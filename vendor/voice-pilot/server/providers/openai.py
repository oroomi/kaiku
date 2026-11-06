"""OpenAI: the Responses API for the tool loop, Chat Completions for any OpenAI-compatible endpoint (NVIDIA NIM / Nemotron, vLLM, llama.cpp,
Ollama), and the Realtime client secret the browser's WebRTC session uses (server/live.py). Plain HTTP with httpx, no SDK needed.

  Responses  POST {base}/responses  {model, instructions, input, tools: [{type: function, name, description, parameters}], tool_choice, stream,
             store: false, reasoning: {effort}, include: [reasoning.encrypted_content]}; output items (reasoning, function_call) are passed back
             unchanged in `input`, results as {type: function_call_output, call_id, output}.
  Chat       POST {base}/chat/completions  {model, messages, tools: [{type: function, function}], tool_choice: auto, stream, stream_options};
             tool_calls stream in pieces by index; the last step sends no tools at all (some servers reject tool_choice "none").
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterator

from .. import config
from .base import ProviderHTTPError, ProviderStreamError, Step, ToolCall, args_of, classify_http, env_key, http_client, stream_json

log = logging.getLogger("voice_pilot.providers.openai")
EFFORTS = {"minimal": "minimal", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}


def openai_key() -> str:
    return env_key("OPENAI_API_KEY")


def local_key(base_url: str = "") -> str:
    """PILOT_LOCAL_API_KEY goes to any endpoint; NVIDIA_API_KEY only to NVIDIA's own hosts (build.nvidia.com's hosted NIM)."""
    from urllib.parse import urlparse
    host = (urlparse(base_url).hostname or "") if base_url else ""
    return env_key("PILOT_LOCAL_API_KEY") or (env_key("NVIDIA_API_KEY") if host == "nvidia.com" or host.endswith(".nvidia.com") else "")


def flat_tools(tools: list[dict]) -> list[dict]:
    """Responses / Realtime function tools: {type, name, description, parameters}."""
    return [{"type": "function", "name": t["name"], "description": t.get("description", ""),
             "parameters": t.get("input_schema") or {"type": "object", "properties": {}}} for t in tools]


class OpenAIBrain:
    name = "openai"
    key_hint = "OPENAI_API_KEY"

    def __init__(self) -> None:
        self._no_extras = False
        self.input: list = []

    def model(self, s: config.Settings) -> str:
        return s.openai_model

    def key_present(self) -> bool:
        return bool(openai_key())

    def make_client(self, s: config.Settings):
        return http_client(s)

    def fake_client(self, script):
        from .fakes import fake_http
        return fake_http("openai", script)

    def begin(self, turn) -> None:
        self.input = [{"role": m["role"], "content": m["content"]} for m in turn.messages]

    def body(self, turn, final: bool) -> dict:
        s = turn.s
        b = {"model": self.model(s), "instructions": turn.system_text(final), "input": self.input,
             "tools": [{**t, "strict": False} for t in flat_tools(turn.tools())], "tool_choice": "none" if final else "auto",
             "stream": True, "store": False, "max_output_tokens": s.max_tokens}
        if not self._no_extras and s.effort in EFFORTS:
            b["reasoning"] = {"effort": EFFORTS[s.effort]}
            b["include"] = ["reasoning.encrypted_content"]
        return b

    def _stream(self, turn, body: dict) -> Iterator[dict]:
        s = turn.s
        turn.new_call()
        done_items: list = []
        final = None
        url = f"{s.openai_base_url.rstrip('/')}/responses"
        for ev, d in stream_json(turn.client, "OpenAI", url, body, {"Authorization": f"Bearer {openai_key()}", "Accept": "text/event-stream"}):
            if not isinstance(d, dict):
                continue
            t = d.get("type") or ev
            if t == "response.output_text.delta":
                yield from turn.say(d.get("delta") or "", turn.steps)
            elif t == "response.output_item.added":
                item = d.get("item") or {}
                if item.get("type") == "function_call" and item.get("name"):
                    yield turn.tool_status(item["name"])
            elif t == "response.output_item.done":
                done_items.append(d.get("item") or {})
            elif t in ("response.completed", "response.incomplete"):
                final = d.get("response") or {}
            elif t == "response.failed":
                err = ((d.get("response") or {}).get("error") or {})
                raise ProviderStreamError(f"{err.get('code', '')}: {err.get('message', '')}")
            elif t == "error":
                if str(d.get("code") or "").startswith("rate_limit"):
                    raise ProviderHTTPError("OpenAI", 429, str(d.get("message") or ""))
                raise ProviderStreamError(f"{d.get('code', '')}: {d.get('message', '')}")
        final = final or {}
        output = final.get("output") or done_items
        calls = [ToolCall(i.get("call_id") or i.get("id") or "", i.get("name") or "", args_of(i.get("arguments")))
                 for i in output if isinstance(i, dict) and i.get("type") == "function_call"]
        refused = any(c.get("type") == "refusal" for i in output if isinstance(i, dict) and i.get("type") == "message"
                      for c in (i.get("content") or []) if isinstance(c, dict))
        reason = (final.get("incomplete_details") or {}).get("reason")
        u = final.get("usage") or {}
        cached = int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        usage = {"input_tokens": int(u.get("input_tokens") or 0) - cached, "output_tokens": int(u.get("output_tokens") or 0),
                 "cache_read_input_tokens": cached}
        stop = "refusal" if (refused or reason == "content_filter") and not turn.text.strip() and not calls else "tool_use" if calls else "end"
        return Step(stop, calls, output, usage, reason or final.get("status"))

    def step(self, turn, final: bool) -> Iterator[dict]:
        try:
            return (yield from self._stream(turn, self.body(turn, final)))
        except ProviderHTTPError as e:
            if e.status == 400 and not self._no_extras and re.search(r"reasoning|effort|include|encrypted", e.text, re.I):
                log.warning("OpenAI refused the reasoning parameters for %s; retrying once without them", self.model(turn.s))
                self._no_extras = True
                return (yield from self._stream(turn, self.body(turn, final)))
            raise

    def push(self, turn, step: Step, results) -> None:
        self.input.extend(i for i in step.raw if isinstance(i, dict))
        self.input.extend({"type": "function_call_output", "call_id": r.call.id, "output": r.body if r.ok else f"ERROR: {r.body}"}
                          for r in results)

    def classify(self, e: Exception, turn) -> dict | None:
        return classify_http(e, turn, "OpenAI")


class _ThinkFilter:
    """Drops <think>...</think> from streamed text (reasoning models served behind Chat Completions, such as some Nemotron builds)."""

    def __init__(self) -> None:
        self.buf, self.inside = "", False

    def feed(self, s: str) -> str:
        self.buf += s
        out = []
        while self.buf:
            tag = "</think>" if self.inside else "<think>"
            i = self.buf.find(tag)
            if i >= 0:
                if not self.inside:
                    out.append(self.buf[:i])
                self.buf, self.inside = self.buf[i + len(tag):], not self.inside
                continue
            keep = next((k for k in range(min(len(tag) - 1, len(self.buf)), 0, -1) if tag.startswith(self.buf[-k:])), 0)   # a tag split across chunks
            if not self.inside:
                out.append(self.buf[:len(self.buf) - keep])
            self.buf = self.buf[len(self.buf) - keep:]
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest


class ChatBrain:
    """Any OpenAI-compatible /chat/completions endpoint. PILOT_BRAIN=local; NVIDIA_API_KEY alone means build.nvidia.com's hosted NIM."""
    name = "local"
    key_hint = "PILOT_LOCAL_BASE_URL"

    def __init__(self) -> None:
        self._no_extras = False
        self.chat: list = []

    def model(self, s: config.Settings) -> str:
        return s.local_model

    def key_present(self) -> bool:
        return bool(env_key("PILOT_LOCAL_BASE_URL", "PILOT_LOCAL_API_KEY", "NVIDIA_API_KEY"))

    def make_client(self, s: config.Settings):
        return http_client(s)

    def fake_client(self, script):
        from .fakes import fake_http
        return fake_http("local", script)

    def begin(self, turn) -> None:
        self.chat = [{"role": m["role"], "content": m["content"]} for m in turn.messages]

    def body(self, turn, final: bool) -> dict:
        s = turn.s
        b = {"model": self.model(s), "messages": [{"role": "system", "content": turn.system_text(final)}, *self.chat], "stream": True,
             "max_tokens": s.max_tokens}
        if not final:
            b["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
                          for t in flat_tools(turn.tools())]
            b["tool_choice"] = "auto"
        if not self._no_extras:
            b["stream_options"] = {"include_usage": True}
        return b

    def _stream(self, turn, body: dict) -> Iterator[dict]:
        s = turn.s
        turn.new_call()
        text, slots, finish, usage = [], {}, None, {}
        think = _ThinkFilter()
        k = local_key(s.local_base_url)
        headers = {"Accept": "text/event-stream", **({"Authorization": f"Bearer {k}"} if k else {})}
        for _ev, d in stream_json(turn.client, "Chat endpoint", f"{s.local_base_url.rstrip('/')}/chat/completions", body, headers):
            if d == "[DONE]":
                break
            if not isinstance(d, dict):
                continue
            if d.get("error"):
                raise ProviderStreamError(str(d["error"])[:300])
            usage = d.get("usage") or usage
            for ch in (d.get("choices") or [])[:1]:
                delta = ch.get("delta") or {}
                piece = think.feed(delta.get("content") or "") if isinstance(delta.get("content"), str) else ""
                if piece:
                    text.append(piece)
                    yield from turn.say(piece, turn.steps)
                for tc in delta.get("tool_calls") or []:
                    k = tc.get("index", len(slots))
                    slot = slots.setdefault(k, {"id": "", "name": "", "arguments": ""})
                    fn = tc.get("function") or {}
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    if fn.get("name"):
                        if not slot["name"]:
                            yield turn.tool_status(fn["name"])
                        slot["name"] = fn["name"]
                    if isinstance(fn.get("arguments"), str):
                        slot["arguments"] += fn["arguments"]
                finish = ch.get("finish_reason") or finish
        tail = think.flush()
        if tail:
            text.append(tail)
            yield from turn.say(tail, turn.steps)
        calls = [ToolCall(v["id"] or f"call_{k}", v["name"], args_of(v["arguments"])) for k, v in sorted(slots.items()) if v["name"]]
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        u = {"input_tokens": int(usage.get("prompt_tokens") or 0) - cached, "output_tokens": int(usage.get("completion_tokens") or 0),
             "cache_read_input_tokens": cached}
        raw = {"role": "assistant", "content": "".join(text) or None,
               **({"tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.args)}} for c in calls]}
                  if calls else {})}
        stop = "refusal" if finish == "content_filter" and not turn.text.strip() and not calls else "tool_use" if calls else "end"
        return Step(stop, calls, raw, u, finish)

    def step(self, turn, final: bool) -> Iterator[dict]:
        try:
            return (yield from self._stream(turn, self.body(turn, final)))
        except ProviderHTTPError as e:
            if e.status in (400, 422) and not self._no_extras and re.search(r"stream_options|include_usage", e.text, re.I):
                log.warning("the endpoint refused stream_options; retrying once without it")
                self._no_extras = True
                return (yield from self._stream(turn, self.body(turn, final)))
            raise

    def push(self, turn, step: Step, results) -> None:
        self.chat.append(step.raw)
        self.chat.extend({"role": "tool", "tool_call_id": r.call.id, "content": r.body if r.ok else f"ERROR: {r.body}"} for r in results)

    def classify(self, e: Exception, turn) -> dict | None:
        return classify_http(e, turn, "Chat endpoint")


# ---- Realtime: an ephemeral client secret for the browser's WebRTC session -----------------------------------------------------------------
def mint_realtime(client, s: config.Settings, system: str, tools: list[dict]) -> dict:
    """POST /v1/realtime/client_secrets with the whole session (model, prompt, tools, voice, input transcript) baked in, so the browser sends no
    session.update. Returns what the browser needs; the API key never leaves the server."""
    session: dict = {"type": "realtime", "model": s.realtime_model, "instructions": system, "tools": flat_tools(tools), "tool_choice": "auto",
                     "audio": {"output": {"voice": s.realtime_voice}}}
    if s.realtime_transcribe:
        session["audio"]["input"] = {"transcription": {"model": s.realtime_transcribe}}
    body = {"expires_after": {"anchor": "created_at", "seconds": max(10, min(7200, s.live_start_s))}, "session": session}
    r = client.post(f"{s.openai_base_url.rstrip('/')}/realtime/client_secrets", json=body, headers={"Authorization": f"Bearer {openai_key()}"})
    if r.status_code != 200:
        raise ProviderHTTPError("OpenAI client_secrets", r.status_code, r.text)
    d = r.json() or {}
    if not d.get("value"):
        raise ProviderStreamError("no value in the client_secrets answer")
    return {"provider": "openai-realtime", "model": s.realtime_model, "token": d["value"], "expires_at": d.get("expires_at"),
            "calls_url": f"{s.openai_base_url.rstrip('/')}/realtime/calls"}
