"""Claude through the Anthropic SDK (the default brain). The request, the stream handling, the one retry without the thinking/fallback parameters
and the error sentences are exactly what server/turn.py did before the provider layer existed; tests/test_server.py pins them."""
from __future__ import annotations

import logging
import re
from typing import Iterator

from .. import config
from ..registry import UI_TOOLS, page_map
from .base import Step, ToolCall

log = logging.getLogger("voice_pilot.turn")


class AnthropicBrain:
    name = "anthropic"
    key_hint = "ANTHROPIC_API_KEY"

    def __init__(self) -> None:
        self._no_extras = False

    def model(self, s: config.Settings) -> str:
        return s.model

    def key_present(self) -> bool:
        return config.anthropic_key_present()

    def make_client(self, s: config.Settings):
        import anthropic
        return anthropic.Anthropic(timeout=s.timeout_s, max_retries=1)   # the SDK reads ANTHROPIC_API_KEY itself

    def fake_client(self, script):
        from ..fake import FakeClient
        return FakeClient(script)

    # -- the request ----------------------------------------------------------------------------------------------------------------------
    def params(self, turn, final: bool) -> dict:
        from ..turn import FINAL_NOTE, system_prompt
        s, m = turn.s, turn.ctx.manifest
        system = [{"type": "text", "text": system_prompt(s, m["app"]["name"], m["app"]["description"], turn.persona),
                   "cache_control": {"type": "ephemeral"}},
                  {"type": "text", "text": "PAGE MAP (what you can show)\n" + page_map(m) + (f"\n\n{FINAL_NOTE}" if final else "")}]
        kw = {"model": s.model, "max_tokens": s.max_tokens, "system": system, "messages": turn.messages,
              "tools": [*UI_TOOLS, *turn.registry.specs()]}
        if final:
            kw["tool_choice"] = {"type": "none"}
        if not self._no_extras:
            if s.thinking == "between_tools":
                kw["thinking"] = {"type": "between_tools"}
            else:
                kw["thinking"] = {"type": "adaptive"}
                if s.effort in ("low", "medium", "high", "xhigh", "max"):
                    kw["output_config"] = {"effort": s.effort}
            if s.fallbacks == "default":
                kw["extra_headers"] = {"anthropic-beta": "server-side-fallback-2026-07-01"}
                kw["extra_body"] = {"fallbacks": "default"}
        return kw

    def _call(self, turn, kw: dict, step: int) -> Iterator[dict]:
        """Stream one model call: text deltas go out as they arrive; returns the final message."""
        turn.new_call()
        with turn.client.messages.stream(**kw) as stream:
            for ev in stream:
                t = getattr(ev, "type", "")
                if t == "content_block_start":
                    blk = getattr(ev, "content_block", None)
                    if getattr(blk, "type", "") == "tool_use":
                        yield turn.tool_status(getattr(blk, "name", ""))
                elif t == "content_block_delta":
                    d = getattr(ev, "delta", None)
                    if getattr(d, "type", "") == "text_delta" and getattr(d, "text", ""):
                        yield from turn.say(d.text, step)
            return stream.get_final_message()

    # -- the provider interface -----------------------------------------------------------------------------------------------------------
    def begin(self, turn) -> None:
        return None                                   # turn.messages is already in the Messages API shape

    def step(self, turn, final: bool) -> Iterator[dict]:
        try:
            import anthropic as sdk
        except ImportError:  # a test with a fake client can run without the SDK
            sdk = None
        s = turn.s
        kw = self.params(turn, final)
        try:
            msg = yield from self._call(turn, kw, turn.steps)
        except Exception as e:  # noqa: BLE001
            bad = sdk is not None and isinstance(e, sdk.BadRequestError)
            if bad and not self._no_extras and re.search(r"thinking|effort|output_config|fallback", str(e), re.I):
                log.warning("the API refused the thinking/fallback parameters for %s; retrying once without them: %s", s.model, str(e)[:200])
                self._no_extras = True
                msg = yield from self._call(turn, self.params(turn, final), turn.steps)
            else:
                raise
        u = getattr(msg, "usage", None)
        usage = {k: int(getattr(u, k, 0) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        content = list(getattr(msg, "content", None) or [])
        raw_stop = getattr(msg, "stop_reason", None)
        uses = [b for b in content if getattr(b, "type", "") == "tool_use"]
        stop = "refusal" if raw_stop == "refusal" else "tool_use" if raw_stop == "tool_use" else "end"
        return Step(stop, [ToolCall(b.id, b.name, getattr(b, "input", {}) or {}) for b in uses], content, usage, raw_stop)

    def push(self, turn, step: Step, results) -> None:
        turn.messages.append({"role": "assistant", "content": step.raw})
        turn.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.call.id, "content": r.body, **({} if r.ok else {"is_error": True})} for r in results]})

    def classify(self, e: Exception, turn) -> dict | None:
        try:
            import anthropic as sdk
        except ImportError:
            return None
        name = turn.s.assistant_name
        if isinstance(e, sdk.APITimeoutError):
            return turn._err("timeout", f"{name} took too long to answer.")
        if isinstance(e, sdk.RateLimitError):
            return turn._err("busy", f"{name} is busy right now. Try again in a moment.")
        if isinstance(e, sdk.AuthenticationError):
            return turn._err("auth", f"{name}'s model key was refused.")
        if isinstance(e, sdk.APIStatusError):
            log.error("Messages API answered %s", getattr(e, "status_code", "?"))
        elif isinstance(e, sdk.APIConnectionError):
            return turn._err("network", f"{name} can't reach the model right now.")
        return None
