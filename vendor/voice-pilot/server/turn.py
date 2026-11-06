"""One voice turn: a short tool loop over the configured brain (Anthropic by default; server/providers/), as a generator of events.

Events (the SSE route writes each as `event: <name>` / `data: <json>`):
  status {label}                        what Aava is doing, for the overlay ("checking the records")
  delta  {text, step}                   answer text as the model writes it; it may hold cue markers like [[2]]
  action {id, type, target?, path?, caption?, value?, ms?}   a validated UI action for the browser; id is the cue number
  error  {kind, message}                a sentence safe to show and speak; the turn ends
  done   {text, actions, steps, ms, usage, model}

The answer is spoken, so it is short (ANSWER_SHAPE). UI tools answer with a cue number and the model places [[n]] at the start of the sentence the
action belongs with; the browser fires the action as that sentence starts playing (docs/ACTIONS.md). Thinking blocks are passed back unchanged.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator

from . import config
from .providers.anthropic import AnthropicBrain
from .providers.base import ToolResult
from .registry import UI_LABELS, UI_TOOL_NAMES, UI_TOOLS, Registry, TurnContext, page_map

log = logging.getLogger("voice_pilot.turn")

ANSWER_SHAPE = (
    "Answer shape, every time: your words are read aloud, so write ONE short paragraph, no line breaks, at most 4 sentences and about 70 words "
    "(a greeting or thanks: one sentence). Lead with the direct answer, name at most 3 things, say why with one concrete fact each, and end with one "
    "next step when it helps. No markdown, no bullets, no emoji, no URLs. Never mention your tools, cues, ids, searches or what they returned, and never "
    "say 'let me highlight': say what the records show while the page shows it. Before your first tool call you may say one short lead-in of "
    "at most 8 words, such as 'Let me pull that up.'; otherwise write nothing until your tool calls are done.")

TOUR_RULES = (
    "You can drive this website while you talk. When the answer is about something on a page, show it: call the UI tools (navigate, scroll_to, "
    "highlight, fill, click, wait) in the order they should happen; you may call several at once. Each valid UI call answers with a cue like [[2]]. "
    "Then write the spoken answer and put each cue at the START of the sentence it belongs with, for example: "
    "\"[[1]] Here are the matches. [[2]] The best one is Kelpforge, at 92, because ... [[3]] Its next step is ...\". "
    "The page acts as that sentence starts playing. Use only page paths and target ids from the PAGE MAP, never CSS selectors; navigate before you "
    "highlight something on another page; click only [safe] targets; fill only [fillable] ones. If a UI call is refused, fix it or skip it. "
    "A question that needs nothing on screen gets no UI calls.")

FINAL_NOTE = "This is your last round: do not call a tool. Write the spoken answer now from what you have, with the cues you already got."
SPOKEN_CUE = re.compile(r"\[\[\s*\d{1,2}\s*\]\]")


def system_prompt(s: config.Settings, app_name: str, app_desc: str, persona: str = "") -> str:
    who = f"You are {s.assistant_name}, the voice assistant inside {app_name or 'this web app'}."
    return "\n\n".join(x for x in [who, app_desc, persona, TOUR_RULES, ANSWER_SHAPE] if x)


def clean_messages(raw, s: config.Settings) -> list[dict]:
    """The conversation as the API wants it: user/assistant text only, the newest a user message. ValueError carries a message safe to show."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages must be a non-empty list")
    out: list[dict] = []
    for m in raw[-s.history_turns:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise ValueError("each message needs a role (user or assistant) and a text content")
        text = " ".join(m["content"].split())
        if text:
            out.append({"role": m["role"], "content": text[:2000]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    if not out or out[-1]["role"] != "user":
        raise ValueError("the last message must be from the user")
    if len(out[-1]["content"]) > s.input_chars:
        raise ValueError(f"a question can be at most {s.input_chars} characters")
    merged: list[dict] = []                       # two user messages in a row (a turn that failed) become one
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {"role": m["role"], "content": merged[-1]["content"] + " " + m["content"]}
        else:
            merged.append(m)
    return merged


def report_note(reports) -> str:
    """Actions the browser could not run last turn, as one line the model reads with the new question."""
    bad = []
    for r in (reports if isinstance(reports, list) else [])[:10]:
        if isinstance(r, dict) and r.get("ok") is False:
            what = " ".join(str(r.get(k) or "") for k in ("type", "target", "path")).strip()[:120]
            bad.append(f"{what} ({str(r.get('why') or 'failed')[:80]})")
    return ("(Note from the page: these actions from your last answer did not run: " + "; ".join(bad) + ".)") if bad else ""


def make_client(s: config.Settings):
    """The default brain's client (Anthropic). Kept here for hosts that import it; other brains build theirs in server/providers/."""
    return AnthropicBrain().make_client(s)


class Turn:
    """One turn, provider-neutral: the brain (server/providers/) makes each model call; this loop runs the tools and streams the events.
    `client` is the brain's client (anthropic.Anthropic or a fake for Claude, an httpx.Client for the HTTP providers)."""

    def __init__(self, messages: list[dict], manifest: dict, registry: Registry, client, s: config.Settings | None = None,
                 persona: str = "", extra: dict | None = None, reports=None, brain=None):
        self.s = s or config.settings()
        self.messages: list = [dict(m) for m in messages]
        note = report_note(reports)
        if note:
            self.messages[-1] = {"role": "user", "content": self.messages[-1]["content"] + "\n\n" + note}
        self.ctx = TurnContext(manifest, extra=extra or {})
        self.registry = registry
        self.client = client
        self.persona = persona
        self.brain = brain or AnthropicBrain()
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        self.steps = 0
        self.text = ""
        self.trace: list[dict] = []
        self._fresh = True

    # -- helpers the brains call while they stream -----------------------------------------------------------------------------------------
    def new_call(self) -> None:
        """A model call starts: its first text may need a separating space."""
        self._fresh = True

    def say(self, piece: str, step: int) -> Iterator[dict]:
        """Answer text as it arrives; a new step's text never glues onto the last word."""
        if not piece:
            return
        if self._fresh and self.text and not self.text.endswith((" ", "\n")):
            self.text += " "
            yield {"event": "delta", "data": {"text": " ", "step": step}}
        self._fresh = False
        self.text += piece
        yield {"event": "delta", "data": {"text": piece, "step": step}}

    def tool_status(self, name: str) -> dict:
        label = UI_LABELS.get(name) if name in UI_TOOL_NAMES else self.registry.label(name)
        return {"event": "status", "data": {"label": label, "tool": name}}

    def tools(self) -> list[dict]:
        """Every tool this turn offers, in the Anthropic shape {name, description, input_schema}; each brain converts it."""
        return [*UI_TOOLS, *self.registry.specs()]

    def system_text(self, final: bool) -> str:
        """The whole system prompt as one string (for brains without separate system blocks)."""
        m = self.ctx.manifest
        return (system_prompt(self.s, m["app"]["name"], m["app"]["description"], self.persona) + "\n\nPAGE MAP (what you can show)\n"
                + page_map(m) + (f"\n\n{FINAL_NOTE}" if final else ""))

    def params(self, final: bool) -> dict:
        """The Anthropic request for this step (kept for hosts that subclassed Turn before the provider layer; Claude brain only)."""
        return self.brain.params(self, final)

    # -- the loop -------------------------------------------------------------------------------------------------------------------------
    def events(self) -> Iterator[dict]:
        s = self.s
        t0 = time.monotonic()
        yield {"event": "status", "data": {"label": "thinking"}}
        final = False
        try:
            self.brain.begin(self)
            while True:
                if time.monotonic() - t0 > s.turn_deadline_s:
                    yield self._err("timeout", f"{s.assistant_name} took too long on that one.")
                    return
                self.steps += 1
                final = final or self.steps >= s.max_steps
                step = yield from self.brain.step(self, final)
                self._usage(step.usage)
                self.trace.append({"step": self.steps, "stop": step.raw_stop,
                                   "tools": [c.name for c in step.calls], "s": round(time.monotonic() - t0, 2)})
                if step.stop == "refusal":
                    yield self._err("refusal", f"{s.assistant_name} can't help with that one.")
                    return
                if step.stop == "tool_use" and step.calls and not final:
                    if self.text and not self.text.endswith((" ", "\n")):     # close the lead-in now, so the browser can speak it while tools run
                        self.text += " "
                        yield {"event": "delta", "data": {"text": " ", "step": self.steps}}
                    results = []
                    for c in step.calls:
                        body, ok, act = self._run(c.name, c.args or {})
                        if act:
                            yield {"event": "action", "data": act}
                        results.append(ToolResult(c, body, ok))
                    self.brain.push(self, step, results)
                    continue
                break
        except Exception as e:  # noqa: BLE001
            yield self._classify(e)
            return
        if not SPOKEN_CUE.sub("", self.text).strip():
            yield self._err("empty", f"{s.assistant_name} did not find words for that one. Try asking another way.")
            return
        ms = round((time.monotonic() - t0) * 1000)
        model = self.brain.model(s)
        log.info("turn %s", json.dumps({"model": model, "steps": self.steps, "ms": ms, "usage": self.usage, "trace": self.trace}))
        yield {"event": "done", "data": {"text": self.text.strip(), "actions": self.ctx.actions, "steps": self.steps, "ms": ms,
                                         "usage": dict(self.usage), "model": model}}

    def _run(self, name: str, args: dict) -> tuple[str, bool, dict | None]:
        if name in UI_TOOL_NAMES:
            act, why = self.ctx.check(name, args, self.s.max_actions)
            if act is None:
                return why, False, None
            n = act["id"]
            return f"Queued as cue [[{n}]]. Put [[{n}]] at the start of the sentence it belongs with.", True, act
        if self.registry.has(name):
            body, ok = self.registry.run(name, args, self.ctx)
            return body, ok, None
        return f"There is no tool called {name}.", False, None

    def _usage(self, u: dict | None) -> None:
        for k in self.usage:
            self.usage[k] += int((u or {}).get(k, 0) or 0)

    def _err(self, kind: str, message: str) -> dict:
        log.warning("turn ended: %s", kind)
        return {"event": "error", "data": {"kind": kind, "message": message}}

    def _classify(self, e: Exception) -> dict:
        out = None
        try:
            out = self.brain.classify(e, self)
        except Exception:  # noqa: BLE001
            out = None
        if out is not None:
            return out
        log.exception("turn failed: %s", type(e).__name__)
        return self._err("api", f"{self.s.assistant_name}'s reasoning is not available right now.")
