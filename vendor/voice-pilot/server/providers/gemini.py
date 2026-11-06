"""Gemini: the standard API (generateContent, streamed as SSE) for the tool loop, and the Live API session the browser opens with an ephemeral
token this server mints (server/live.py). Plain HTTP with httpx, no SDK needed.

  POST {base}/v1beta/models/{model}:streamGenerateContent?alt=sse     header x-goog-api-key
       {systemInstruction, contents, tools: [{functionDeclarations}], toolConfig: {functionCallingConfig: {mode}}, generationConfig}
  The model's parts are passed back exactly as received (thought signatures ride on them); results go back as functionResponse parts with the
  call's id. Function parameters are an OpenAPI subset, so `additionalProperties` is dropped from the UI tool schemas.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterator
from urllib.parse import quote

from .. import config
from .base import ProviderHTTPError, ProviderStreamError, Step, ToolCall, args_of, classify_http, env_key, http_client, stream_json, strip_schema

log = logging.getLogger("voice_pilot.providers.gemini")

SCHEMA_KEYS = frozenset({"type", "description", "properties", "required", "enum", "items", "format", "nullable", "minimum", "maximum"})
REFUSE = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}
LEVELS = {"minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


def key() -> str:
    return env_key("GEMINI_API_KEY", "GOOGLE_API_KEY")


def declarations(tools: list[dict]) -> list[dict]:
    """Function declarations; a tool without arguments gets no `parameters` (Gemini refuses an OBJECT with empty properties)."""
    out = []
    for t in tools:
        d = {"name": t["name"], "description": t.get("description", "")}
        params = strip_schema(t.get("input_schema") or {}, SCHEMA_KEYS)
        if params.get("properties"):
            d["parameters"] = params
        out.append(d)
    return out


class GeminiBrain:
    name = "gemini"
    key_hint = "GEMINI_API_KEY"

    def __init__(self) -> None:
        self._no_extras = False
        self.contents: list[dict] = []
        self._ids = 0

    def model(self, s: config.Settings) -> str:
        return s.gemini_model

    def key_present(self) -> bool:
        return bool(key())

    def make_client(self, s: config.Settings):
        return http_client(s)

    def fake_client(self, script):
        from .fakes import fake_http
        return fake_http("gemini", script)

    def begin(self, turn) -> None:
        self.contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in turn.messages]

    def body(self, turn, final: bool) -> dict:
        s = turn.s
        b = {"systemInstruction": {"parts": [{"text": turn.system_text(final)}]}, "contents": self.contents,
             "tools": [{"functionDeclarations": declarations(turn.tools())}],
             "toolConfig": {"functionCallingConfig": {"mode": "NONE" if final else "AUTO"}},
             "generationConfig": {"maxOutputTokens": s.max_tokens}}
        if not self._no_extras and s.effort in LEVELS and s.gemini_thinking != "off":
            b["generationConfig"]["thinkingConfig"] = {"thinkingLevel": LEVELS[s.effort]}
        return b

    def _stream(self, turn, body: dict) -> Iterator[dict]:
        s = turn.s
        turn.new_call()
        url = f"{s.gemini_base_url.rstrip('/')}/v1beta/models/{quote(self.model(s), safe='')}:streamGenerateContent?alt=sse"
        parts: list = []
        calls: list[ToolCall] = []
        finish, usage, blocked = None, {}, None
        for _ev, chunk in stream_json(turn.client, "Gemini", url, body, {"x-goog-api-key": key(), "Accept": "text/event-stream"}):
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                raise ProviderStreamError(str(chunk["error"])[:300])
            blocked = blocked or (chunk.get("promptFeedback") or {}).get("blockReason")
            usage = chunk.get("usageMetadata") or usage
            for cand in (chunk.get("candidates") or [])[:1]:
                for p in ((cand.get("content") or {}).get("parts") or []):
                    if not isinstance(p, dict):
                        continue
                    parts.append(p)
                    fc = p.get("functionCall")
                    if isinstance(fc, dict) and fc.get("name"):
                        cid = fc.get("id")
                        if not cid:
                            self._ids += 1
                        calls.append(ToolCall(cid or f"call_{self._ids}", fc["name"], args_of(fc.get("args")), native_id=bool(cid)))
                        yield turn.tool_status(fc["name"])
                    elif isinstance(p.get("text"), str) and not p.get("thought"):
                        yield from turn.say(p["text"], turn.steps)
                finish = cand.get("finishReason") or finish
        u = {"input_tokens": int(usage.get("promptTokenCount") or 0) - int(usage.get("cachedContentTokenCount") or 0),
             "output_tokens": int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
             "cache_read_input_tokens": int(usage.get("cachedContentTokenCount") or 0)}
        stop = "refusal" if (blocked or finish in REFUSE) and not turn.text.strip() and not calls else "tool_use" if calls else "end"
        return Step(stop, calls, parts, u, finish or blocked)

    def step(self, turn, final: bool) -> Iterator[dict]:
        try:
            return (yield from self._stream(turn, self.body(turn, final)))
        except ProviderHTTPError as e:
            if e.status == 400 and not self._no_extras and re.search(r"thinking|thought", e.text, re.I):
                log.warning("Gemini refused the thinking config for %s; retrying once without it", self.model(turn.s))
                self._no_extras = True
                return (yield from self._stream(turn, self.body(turn, final)))
            raise

    def push(self, turn, step: Step, results) -> None:
        self.contents.append({"role": "model", "parts": step.raw})
        self.contents.append({"role": "user", "parts": [
            {"functionResponse": {**({"id": r.call.id} if r.call.native_id else {}), "name": r.call.name,
                                  "response": {"output": r.body} if r.ok else {"error": r.body}}} for r in results]})

    def classify(self, e: Exception, turn) -> dict | None:
        return classify_http(e, turn, "Gemini")


# ---- the Live API: an ephemeral token for the browser, locked to our setup --------------------------------------------------------------
LIVE_WS = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def live_setup(s: config.Settings, system: str, tools: list[dict]) -> dict:
    """The first WebSocket message (BidiGenerateContentSetup): native audio out, both transcripts on, our tools, our system prompt."""
    gen: dict = {"responseModalities": ["AUDIO"]}
    if s.live_voice_name:
        gen["speechConfig"] = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": s.live_voice_name}}}
    return {"setup": {"model": f"models/{s.gemini_live_model}", "generationConfig": gen,
                      "systemInstruction": {"parts": [{"text": system}]}, "tools": [{"functionDeclarations": declarations(tools)}],
                      "inputAudioTranscription": {}, "outputAudioTranscription": {}}}


def mint_live(client, s: config.Settings, system: str, tools: list[dict]) -> dict:
    """POST /v1beta/auth_tokens: a one-use token whose Live session is locked to this model, prompt and tool list. Returns what the browser needs
    (the token is short-lived and can open one session; the API key never leaves the server)."""
    now = datetime.now(timezone.utc)
    setup = live_setup(s, system, tools)
    st = setup["setup"]
    cfg = {"responseModalities": st["generationConfig"]["responseModalities"], "systemInstruction": st["systemInstruction"], "tools": st["tools"],
           "inputAudioTranscription": {}, "outputAudioTranscription": {}}
    if "speechConfig" in st["generationConfig"]:
        cfg["speechConfig"] = st["generationConfig"]["speechConfig"]
    body = {"uses": 1, "expireTime": _iso(now + timedelta(minutes=30)), "newSessionExpireTime": _iso(now + timedelta(seconds=s.live_start_s)),
            "liveConnectConstraints": {"model": st["model"], "config": cfg}}
    r = client.post(f"{s.gemini_base_url.rstrip('/')}/v1beta/auth_tokens", json=body, headers={"x-goog-api-key": key()})
    if r.status_code != 200:
        raise ProviderHTTPError("Gemini auth_tokens", r.status_code, r.text)
    token = (r.json() or {}).get("name") or ""
    if not token:
        raise ProviderStreamError("no token in the auth_tokens answer")
    return {"provider": "gemini-live", "model": s.gemini_live_model, "url": f"{LIVE_WS}?access_token={quote(token, safe='')}",
            "setup": setup, "expires_at": body["expireTime"]}
