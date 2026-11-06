"""The provider interface: one model call of the tool loop (a "step"), in a shape every brain can fill.

A brain turns the provider-neutral turn (server/turn.py: the conversation, the page map, the tools) into its own request, streams the answer text
out through `turn.say()` as it arrives, and hands back a Step: why it stopped, the tool calls it made, and the token usage. The loop in turn.py runs
the tools (data tools on the server, UI tools validated against the page) and gives the results back with `push()`. Nothing in turn.py knows which
provider it is talking to.

    class Brain:
        name                       "gemini"
        model(s)                   the model id this brain sends
        key_present()              a key (or a local endpoint) is configured; booleans only, a key is never returned
        key_hint                   the variable to name in "not switched on yet" messages
        make_client(s)             the real client (httpx.Client for the HTTP providers, anthropic.Anthropic for Claude)
        fake_client(script)        a stand-in answering from a script (tests, rehearsal): the same wire format, no network
        begin(turn)                the provider's own history from turn.messages
        step(turn, final)          generator: yields events (delta, status), returns a Step
        push(turn, step, results)  the step's own output plus the tool results, appended to the history
        classify(e, turn)          an exception as an error event (a sentence safe to show and speak)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterator

log = logging.getLogger("voice_pilot.providers")


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    native_id: bool = True        # False when the provider sent no id and we made one up (Gemini without ids)


@dataclass
class Step:
    stop: str                     # "tool_use" | "end" | "refusal"
    calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None               # the provider's own output for this step, passed back unchanged (thought signatures, reasoning items)
    usage: dict = field(default_factory=dict)
    raw_stop: Any = None          # the provider's own stop reason, for the turn log


@dataclass
class ToolResult:
    call: ToolCall
    body: str
    ok: bool


class ProviderHTTPError(Exception):
    """A non-200 answer from a provider. `text` is the start of the body (an error message, never a key)."""

    def __init__(self, provider: str, status: int, text: str = "") -> None:
        super().__init__(f"{provider} answered {status}: {text[:300]}")
        self.provider, self.status, self.text = provider, status, text[:2000]


class ProviderStreamError(Exception):
    """An error event inside a 200 stream (OpenAI `error` / `response.failed`, a Gemini error chunk)."""


def env_key(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def iter_sse(lines: Iterator[str]) -> Iterator[tuple[str, str]]:
    """(event, data) pairs from SSE lines. A block without `event:` is ("message", data). "[DONE]" is passed through as data."""
    ev, data = "message", []
    for line in lines:
        line = line.rstrip("\r")
        if not line:
            if data:
                yield ev, "\n".join(data)
            ev, data = "message", []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" ") if line[5:6] == " " else line[5:])
    if data:
        yield ev, "\n".join(data)


def stream_json(client, provider: str, url: str, body: dict, headers: dict) -> Iterator[tuple[str, Any]]:
    """POST and read the SSE answer as (event, parsed JSON | "[DONE]"). A non-200 answer raises ProviderHTTPError before anything is read."""
    with client.stream("POST", url, json=body, headers=headers) as r:
        if r.status_code != 200:
            r.read()
            raise ProviderHTTPError(provider, r.status_code, r.text)
        for ev, data in iter_sse(r.iter_lines()):
            if data.strip() == "[DONE]":
                yield ev, "[DONE]"
                continue
            try:
                yield ev, json.loads(data)
            except ValueError:
                log.warning("%s sent a stream line that is not JSON", provider)


def http_client(s):
    import httpx
    return httpx.Client(timeout=httpx.Timeout(s.timeout_s, connect=min(10.0, s.timeout_s)))


def classify_http(e: Exception, turn, provider: str) -> dict | None:
    """The shared error sentences for the HTTP providers (the same words the Anthropic path uses)."""
    import httpx
    name = turn.s.assistant_name
    if isinstance(e, ProviderHTTPError):
        if e.status in (401, 403):
            return turn._err("auth", f"{name}'s model key was refused.")
        if e.status == 429:
            return turn._err("busy", f"{name} is busy right now. Try again in a moment.")
        if e.status in (408, 504):
            return turn._err("timeout", f"{name} took too long to answer.")
        log.error("%s answered %s", provider, e.status)
        return turn._err("api", f"{name}'s reasoning is not available right now.")
    if isinstance(e, httpx.TimeoutException):
        return turn._err("timeout", f"{name} took too long to answer.")
    if isinstance(e, httpx.TransportError):
        return turn._err("network", f"{name} can't reach the model right now.")
    if isinstance(e, ProviderStreamError):
        log.error("%s stream error: %s", provider, str(e)[:200])
        return turn._err("api", f"{name}'s reasoning is not available right now.")
    return None


def strip_schema(schema: Any, keep: frozenset) -> Any:
    """A JSON schema with only the keys a provider accepts (Gemini's function parameters are an OpenAPI subset: no additionalProperties)."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k not in keep:
                continue
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: strip_schema(pv, keep) for pk, pv in v.items()}
            elif k == "items":
                out[k] = strip_schema(v, keep)
            else:
                out[k] = v
        return out
    return schema


def args_of(raw: Any) -> dict:
    """Tool arguments as a dict, from a dict or a JSON string; anything else is {}."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}
