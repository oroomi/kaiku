"""Fake provider endpoints for tests and rehearsal mode: an httpx.Client whose transport answers in-process, in each provider's own wire format.

The script is the same one the Anthropic fake (server/fake.py) takes: a list of `reply(...)` values or a callable(view) -> reply, where `view` has
the Anthropic shape of the request ({"messages": [..., the last message with tool_result blocks], "final": bool}) plus the raw request (`body`,
`url`, `headers`). So one script (and the rehearsal plan) drives every brain, and the real request builders and stream parsers run unchanged.
Every request is kept in `.calls` as {"url", "headers", "body"}.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import httpx


class HTTPReply:
    """A non-200 answer: `script` may hold one of these to test error handling."""

    def __init__(self, status: int, text: str = "") -> None:
        self.status, self.text = status, text


def _pieces(b) -> list[str]:
    if getattr(b, "chunks", None):
        return list(b.chunks)
    words = b.text.split(" ")
    return [" ".join(words[j:j + 3]) + (" " if j + 3 < len(words) else "") for j in range(0, len(words), 3)]


def _sse(events: list, named: bool = False) -> bytes:
    out = []
    for e in events:
        if e == "[DONE]":
            out.append("data: [DONE]\n\n")
        elif named:
            out.append(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n")
        else:
            out.append(f"data: {json.dumps(e)}\n\n")
    return "".join(out).encode()


# ---- the request as the Anthropic-shaped view the scripts read --------------------------------------------------------------------------
def _result(call_id: str, content: str, err: bool) -> dict:
    return {"type": "tool_result", "tool_use_id": call_id, "content": content, **({"is_error": True} if err else {})}


def view(kind: str, body: dict) -> dict:
    results: list = []
    text = ""
    if kind == "gemini":
        last = (body.get("contents") or [{}])[-1]
        for p in last.get("parts") or []:
            fr = p.get("functionResponse")
            if fr:
                r = fr.get("response") or {}
                results.append(_result(fr.get("id") or fr.get("name"), str(r.get("output", r.get("error", ""))), "error" in r))
            elif "text" in p:
                text += p["text"]
        final = (body.get("toolConfig") or {}).get("functionCallingConfig", {}).get("mode") == "NONE"
    elif kind == "openai":
        items = body.get("input") or []
        for i in reversed(items):
            if isinstance(i, dict) and i.get("type") == "function_call_output":
                o = str(i.get("output") or "")
                results.insert(0, _result(i["call_id"], o[7:] if o.startswith("ERROR: ") else o, o.startswith("ERROR: ")))
            else:
                break
        if not results and items:
            text = str(items[-1].get("content") or "")
        final = body.get("tool_choice") == "none"
    else:
        msgs = body.get("messages") or []
        for m in reversed(msgs):
            if m.get("role") == "tool":
                o = str(m.get("content") or "")
                results.insert(0, _result(m["tool_call_id"], o[7:] if o.startswith("ERROR: ") else o, o.startswith("ERROR: ")))
            else:
                break
        if not results and msgs:
            text = str(msgs[-1].get("content") or "")
        final = "tools" not in body
    last_msg = {"role": "user", "content": results} if results else {"role": "user", "content": text}
    return {"messages": [last_msg], "final": final, "body": body}


# ---- a scripted reply in each wire format ------------------------------------------------------------------------------------------------
def _gemini(r: dict) -> bytes:
    ev = []
    for b in r["content"]:
        if b.type == "text":
            ev += [{"candidates": [{"content": {"role": "model", "parts": [{"text": p}]}, "index": 0}]} for p in _pieces(b)]
        elif b.type == "tool_use":
            ev.append({"candidates": [{"content": {"role": "model", "parts": [
                {"functionCall": {"id": b.id, "name": b.name, "args": b.input}, "thoughtSignature": f"sig-{b.id}"}]}, "index": 0}]})
    finish = "SAFETY" if r["stop_reason"] == "refusal" else "STOP"
    ev.append({"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": finish, "index": 0}],
               "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 40, "totalTokenCount": 140}})
    return _sse(ev)


def _openai(r: dict) -> bytes:
    ev: list = [{"type": "response.created", "response": {"status": "in_progress"}}]
    output = []
    text = "".join(b.text for b in r["content"] if b.type == "text")
    if r["stop_reason"] == "refusal":
        output.append({"type": "message", "id": "msg_1", "role": "assistant", "content": [{"type": "refusal", "refusal": "No."}]})
    elif text:
        msg = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text}]}
        ev.append({"type": "response.output_item.added", "item": {**msg, "content": []}})
        for b in r["content"]:
            if b.type == "text":
                ev += [{"type": "response.output_text.delta", "item_id": "msg_1", "delta": p} for p in _pieces(b)]
        ev.append({"type": "response.output_item.done", "item": msg})
        output.append(msg)
    for b in r["content"]:
        if b.type == "tool_use":
            item = {"type": "function_call", "id": f"fc_{b.id}", "call_id": b.id, "name": b.name, "arguments": json.dumps(b.input),
                    "status": "completed"}
            ev.append({"type": "response.output_item.added", "item": {**item, "arguments": ""}})
            ev.append({"type": "response.function_call_arguments.done", "item_id": item["id"], "arguments": item["arguments"]})
            ev.append({"type": "response.output_item.done", "item": item})
            output.append(item)
    ev.append({"type": "response.completed", "response": {"status": "completed", "output": output,
                                                          "usage": {"input_tokens": 100, "output_tokens": 40, "input_tokens_details": {"cached_tokens": 0}}}})
    return _sse(ev, named=True)


def _chat(r: dict) -> bytes:
    ev: list = []
    for b in r["content"]:
        if b.type == "text":
            ev += [{"choices": [{"index": 0, "delta": {"content": p}}]} for p in _pieces(b)]
    k = 0
    for b in r["content"]:
        if b.type == "tool_use":
            a = json.dumps(b.input)
            ev.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": k, "id": b.id, "type": "function",
                                                                           "function": {"name": b.name, "arguments": a[: len(a) // 2]}}]}}]})
            ev.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": k, "function": {"arguments": a[len(a) // 2:]}}]}}]})
            k += 1
    finish = "content_filter" if r["stop_reason"] == "refusal" else "tool_calls" if k else "stop"
    ev.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    ev.append({"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 40}})
    ev.append("[DONE]")
    return _sse(ev)


ENCODERS = {"gemini": _gemini, "openai": _openai, "local": _chat}


class FakeHTTP(httpx.Client):
    def __init__(self, kind: str, script) -> None:
        self.calls: list[dict] = []
        self._kind, self._script = kind, script
        super().__init__(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        v = view(self._kind, body)
        r = self._script(v) if callable(self._script) else self._script.pop(0)
        if isinstance(r, HTTPReply):
            return httpx.Response(r.status, text=r.text)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=ENCODERS[self._kind](r))


def fake_http(kind: str, script) -> FakeHTTP:
    return FakeHTTP(kind, script)


__all__ = ["HTTPReply", "FakeHTTP", "fake_http", "view", "NS"]
