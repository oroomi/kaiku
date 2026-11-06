"""The HTTP surface, as one APIRouter a host FastAPI app includes:

    from server.router import make_router, mount_client
    from server.registry import Registry

    registry = Registry()                              # register the app's read-only data tools on it
    app.include_router(make_router(registry, app_name="My app", app_description="What it does, one sentence."))
    mount_client(app)                                  # serves client/pilot.js and pilot.css at /pilot/client/

  GET  /pilot/status  {llm, mode, model, tts, tts_chars_left, name}   booleans and names only, never a key
                      (+ brain, voice, live when PILOT_BRAIN or PILOT_VOICE is set; the default answer is unchanged)
  POST /pilot/chat    {messages, manifest, reports} -> text/event-stream: status, delta, action, error, done
  POST /pilot/tts     {text} -> audio/mpeg (ElevenLabs), or 404/429/502 JSON so the browser uses its own voice
  POST /pilot/live/session, /pilot/live/tools   the live voices (Gemini Live, OpenAI Realtime): see server/live.py
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import config
from . import live as live_mod
from .fake import Plan, rehearsal_client, rehearsal_script
from .limits import Limiter, client_ip
from .providers import chat_brain
from .providers.base import ProviderHTTPError, http_client
from .registry import Registry, clean_manifest
from .tts import Voice
from .turn import Turn, clean_messages, make_client

log = logging.getLogger("voice_pilot.http")
SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class PilotState:
    registry: Registry
    app_name: str = ""
    app_description: str = ""
    persona: str = ""
    rehearsal_plan: Plan | None = None
    extra: Callable[[Request], dict] | None = None
    limiter: Limiter = field(default_factory=Limiter)
    voice: Voice | None = None
    # (settings, question, manifest) -> the brain's client (.messages.stream(**kw) for Claude, an httpx.Client for the HTTP brains). Tests
    # replace it with a fake.
    client_factory: Callable | None = None
    # (settings) -> an httpx.Client for minting live credentials. Tests replace it with a fake transport.
    live_http: Callable | None = None
    sessions: live_mod.Sessions = field(default_factory=live_mod.Sessions)

    def mode(self, s: config.Settings) -> str:
        if s.rehearsal:
            return "rehearsal"
        if s.brain == "anthropic":
            return "live" if config.anthropic_key_present() else "off"
        return "live" if chat_brain(s.brain).key_present() else "off"

    def client(self, s: config.Settings, question: str, manifest: dict, brain=None):
        if self.client_factory is not None:
            return self.client_factory(s, question, manifest)
        if s.brain == "anthropic":
            if s.rehearsal:
                return rehearsal_client(self.rehearsal_plan, question, manifest, s.assistant_name)
            return make_client(s)
        brain = brain or chat_brain(s.brain)
        if s.rehearsal:                                # the brain's own wire format, answered in-process from the plan
            return brain.fake_client(rehearsal_script(self.rehearsal_plan, question, manifest, s.assistant_name))
        return brain.make_client(s)


def make_router(registry: Registry, *, prefix: str = "/pilot", app_name: str = "", app_description: str = "", persona: str = "",
                rehearsal_plan: Plan | None = None, extra: Callable[[Request], dict] | None = None) -> APIRouter:
    router = APIRouter()
    st = PilotState(registry, app_name, app_description, persona, rehearsal_plan, extra)
    st.voice = Voice(st.limiter)
    router.pilot = st  # type: ignore[attr-defined]   (tests and hosts reach the state here)

    @router.get(f"{prefix}/status")
    def status():
        s = config.settings()
        tts = bool(config.elevenlabs_key() and s.tts_voice_id) and s.voice != "browser"
        model = (s.model if s.brain == "anthropic" else chat_brain(s.brain).model(s)) if st.mode(s) == "live" else None
        out = {"name": s.assistant_name, "mode": st.mode(s), "llm": st.mode(s) != "off", "model": model,
               "tts": tts, "tts_chars_left": st.limiter.tts_left(s.tts_daily_chars) if tts else 0}
        if s.brain != "anthropic" or s.voice_explicit:           # the default answer stays byte for byte what it was
            out.update({"brain": s.brain, "voice": s.voice, "live": s.live if (s.live and not s.rehearsal and st.mode(s) == "live") else None})
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    def refuse(kind: str, message: str, code: int, headers: dict | None = None):
        def gen():
            yield sse("error", {"kind": kind, "message": message})
        return StreamingResponse(gen(), status_code=code, media_type="text/event-stream", headers={**SSE_HEADERS, **(headers or {})})

    def too_big(request: Request, limit: int) -> bool:
        try:
            return int(request.headers.get("content-length") or 0) > limit
        except ValueError:
            return True

    @router.post(f"{prefix}/chat")
    async def chat(request: Request):
        s = config.settings()
        if too_big(request, 256_000):
            return JSONResponse({"error": "the request is too large"}, status_code=413)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "send a JSON body {messages, manifest}"}, status_code=400)
        try:
            messages = clean_messages(body.get("messages"), s)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        manifest = clean_manifest(body.get("manifest"))
        if st.app_name and not manifest["app"]["name"]:
            manifest["app"]["name"] = st.app_name
        if st.app_description and not manifest["app"]["description"]:
            manifest["app"]["description"] = st.app_description
        if st.mode(s) == "off" and st.client_factory is None:
            need = "ANTHROPIC_API_KEY" if s.brain == "anthropic" else chat_brain(s.brain).key_hint
            return refuse("no_key", f"{s.assistant_name}'s reasoning is not switched on yet: the server needs {need}.", 200)
        refused = st.limiter.check(client_ip(request, s.trust_proxy), s.rate_per_min, s.daily_turns)
        if refused == "rate":
            return refuse("rate", "That is a lot of questions in a minute. Give me a moment and ask again.", 429, {"Retry-After": "30"})
        if refused == "cap":
            return refuse("cap", f"{s.assistant_name} has answered all the questions it can for today.", 429, {"Retry-After": "3600"})
        question = messages[-1]["content"]
        brain = chat_brain(s.brain)
        try:
            client = st.client(s, question, manifest, brain)
        except Exception:  # noqa: BLE001
            log.exception("could not build the model client")
            return refuse("api", f"{s.assistant_name}'s reasoning is not available right now.", 200)
        turn = Turn(messages, manifest, st.registry, client, s, persona=st.persona, extra=(st.extra(request) if st.extra else {}),
                    reports=body.get("reports"), brain=brain)

        def gen():
            try:
                for ev in turn.events():
                    yield sse(ev["event"], ev["data"])
            except Exception:  # noqa: BLE001
                log.exception("stream failed")
                yield sse("error", {"kind": "internal", "message": f"{s.assistant_name} hit a snag."})

        return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)

    @router.post(f"{prefix}/tts")
    async def tts(request: Request):
        s = config.settings()
        if too_big(request, 16_000):
            return JSONResponse({"error": "the request is too large"}, status_code=413)
        if not st.limiter.tts_rate(client_ip(request, s.trust_proxy), s.tts_rate_per_min):
            return JSONResponse({"error": "too many voice requests this minute; the browser voice is used"}, status_code=429, headers={"Retry-After": "30"})
        try:
            body = await request.json()
            text = body.get("text") if isinstance(body, dict) else None
        except Exception:  # noqa: BLE001
            text = None
        if not isinstance(text, str):
            return JSONResponse({"error": "send {text}"}, status_code=400)
        if s.voice == "browser":
            return JSONResponse({"error": "PILOT_VOICE=browser: the browser voice is used"}, status_code=404)
        return await st.voice.respond(text)

    # ---- live voices (server/live.py) -----------------------------------------------------------------------------------------------------
    async def _json(request: Request, limit: int):
        if too_big(request, limit):
            return None, JSONResponse({"error": "the request is too large"}, status_code=413)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
            return body, None
        except Exception:  # noqa: BLE001
            return None, JSONResponse({"error": "send a JSON body"}, status_code=400)

    @router.post(f"{prefix}/live/session")
    async def live_session(request: Request):
        s = config.settings()
        if not s.live:
            return JSONResponse({"error": "no live voice is configured (PILOT_VOICE)"}, status_code=404)
        if s.rehearsal:
            return JSONResponse({"error": "rehearsal mode uses the classic voice path"}, status_code=409)
        if st.mode(s) != "live":
            return JSONResponse({"error": f"the server needs {chat_brain(s.brain).key_hint} for the live voice"}, status_code=503)
        body, bad = await _json(request, 256_000)
        if bad:
            return bad
        manifest = clean_manifest(body.get("manifest"))
        if st.app_name and not manifest["app"]["name"]:
            manifest["app"]["name"] = st.app_name
        if st.app_description and not manifest["app"]["description"]:
            manifest["app"]["description"] = st.app_description
        ip = client_ip(request, s.trust_proxy)
        refused = st.limiter.check(ip, s.rate_per_min, s.daily_turns)
        if refused:
            return JSONResponse({"error": "too many live sessions; try again in a moment" if refused == "rate" else "the daily limit is used up"},
                                status_code=429, headers={"Retry-After": "30" if refused == "rate" else "3600"})
        if not st.sessions.room(s.live_daily_sessions):
            return JSONResponse({"error": "the live voice has used all its sessions for today"}, status_code=429, headers={"Retry-After": "3600"})
        system = live_mod.live_system(s, manifest, st.persona)
        tools = live_mod.live_tools(st.registry)
        from starlette.concurrency import run_in_threadpool

        def mint():
            client = st.live_http(s) if st.live_http else http_client(s)
            try:
                if s.live == "gemini-live":
                    from .providers.gemini import mint_live
                    return mint_live(client, s, system, tools)
                from .providers.openai import mint_realtime
                return mint_realtime(client, s, system, tools)
            finally:
                client.close()
        try:
            out = await run_in_threadpool(mint)
        except ProviderHTTPError as e:
            log.warning("minting the live credential failed: %s %s", e.provider, e.status)
            return JSONResponse({"error": f"the live voice service answered {e.status}"}, status_code=502)
        except Exception as e:  # noqa: BLE001
            log.warning("minting the live credential failed: %s", type(e).__name__)
            return JSONResponse({"error": "the live voice service is not reachable"}, status_code=502)
        out["session"] = st.sessions.create(ip)
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    @router.post(f"{prefix}/live/tools")
    async def live_tools(request: Request):
        s = config.settings()
        body, bad = await _json(request, 256_000)
        if bad:
            return bad
        calls = body.get("calls")
        if not isinstance(calls, list) or not calls or len(calls) > 16:
            return JSONResponse({"error": "send {session, calls: [1-16 calls], manifest}"}, status_code=400)
        if not st.limiter.live_rate(client_ip(request, s.trust_proxy), s.live_tool_rate_per_min):
            return JSONResponse({"error": "too many tool calls this minute"}, status_code=429, headers={"Retry-After": "30"})
        why = st.sessions.charge(body.get("session"), len(calls), s.live_max_calls)
        if why:
            return JSONResponse({"error": "the live session has ended" if why == "unknown" else "this live session has used all its tool calls"},
                                status_code=403)
        manifest = clean_manifest(body.get("manifest"))
        from starlette.concurrency import run_in_threadpool
        results = await run_in_threadpool(live_mod.run_calls, calls, manifest, st.registry, s, st.extra(request) if st.extra else {})
        return JSONResponse({"results": results}, headers={"Cache-Control": "no-store"})

    return router


def mount_client(app, prefix: str = "/pilot") -> None:
    """Serve client/pilot.js, pilot.global.js and pilot.css at {prefix}/client/."""
    from fastapi.staticfiles import StaticFiles
    app.mount(f"{prefix}/client", StaticFiles(directory=str(CLIENT_DIR)), name="pilot-client")
