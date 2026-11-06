"""Live voice sessions (PILOT_VOICE=gemini-live or openai-realtime): the browser talks to the model directly, full duplex, and this server only
mints the short-lived credential and runs the tools.

  POST /pilot/live/session  {manifest}                       -> {provider, session, model, url+setup (Gemini) | token+calls_url (OpenAI), expires_at}
  POST /pilot/live/tools    {session, calls: [{id, name, args}], manifest}
                                                             -> {results: [{id, name, ok, output, action}]}

The session's system prompt and tool list are baked into the credential. Gemini's token is locked to them; OpenAI's client secret carries the
session, but a browser holding it could still send session.update and change the prompt or voice. Either way the page cannot get past the
tools: every call is validated here, and a live session costs one question against the per-IP and daily limits plus PILOT_LIVE_DAILY_SESSIONS.
Session ids live in memory, per process (run one worker, or pin visitors to one). Each tool call the model makes in the browser comes back here: UI tools are validated against the page
manifest exactly as in /pilot/chat (TurnContext.check) and come back as an action the browser runs before it answers the model; data tools run in
the registry. One request holds all the calls of one model message, so `navigate` then `highlight` is checked against the destination page.
Unlike the cue timing of /pilot/chat, a live action happens when the model calls it: the model calls first and then talks about what is on screen.
"""
from __future__ import annotations

import secrets
import threading
import time

from . import config
from .registry import UI_TOOL_NAMES, UI_TOOLS, Registry, TurnContext, page_map

LIVE_RULES = (
    "You can drive this website while you talk. When the answer is about something on a page, show it: call the UI tools (navigate, scroll_to, "
    "highlight, fill, click, wait) and the page acts at once, so call the tool first and then talk about what the page now shows. You may call "
    "several at once, in the order they should happen. Navigate before you highlight something on another page; a navigate result lists the "
    "targets on the new page. Use only page paths and target ids from the PAGE MAP or a tool result, never CSS selectors; click only [safe] "
    "targets; fill only [fillable] ones. If a UI call is refused, fix it or skip it. A question that needs nothing on screen gets no UI calls.")

LIVE_SHAPE = (
    "This is a live spoken conversation and the person can interrupt you: answer in at most 4 short sentences, lead with the direct answer, name at "
    "most 3 things with one concrete fact each, and end with one next step when it helps. Never read out ids, paths, tool names or what the tools "
    "returned, and never say 'let me highlight': say what the records show while the page shows it. If you are interrupted, stop and answer the "
    "new question. Before a tool call you may say a lead-in of at most 8 words.")


def live_system(s: config.Settings, manifest: dict, persona: str = "") -> str:
    m = manifest
    who = f"You are {s.assistant_name}, the voice assistant inside {m['app']['name'] or 'this web app'}."
    head = "\n\n".join(x for x in [who, m["app"]["description"], persona, LIVE_RULES, LIVE_SHAPE] if x)
    return head + "\n\nPAGE MAP (what you can show)\n" + page_map(m)


def live_tools(registry: Registry) -> list[dict]:
    return [*UI_TOOLS, *registry.specs()]


class Sessions:
    """Live session ids handed out with a credential: in memory, per process, expiring with the credential's longest life."""

    def __init__(self, ttl_s: float = 35 * 60) -> None:
        self.ttl, self.lock, self.items = ttl_s, threading.Lock(), {}
        self.day, self.today = "", 0

    def room(self, daily_cap: int) -> bool:
        """True when another live session may start today (UTC); counts it."""
        from .limits import _today
        with self.lock:
            if self.day != _today():
                self.day, self.today = _today(), 0
            if self.today >= daily_cap:
                return False
            self.today += 1
            return True

    def create(self, ip: str) -> str:
        sid = secrets.token_urlsafe(18)
        now = time.monotonic()
        with self.lock:
            self.items = {k: v for k, v in self.items.items() if v["exp"] > now} if len(self.items) > 2000 else self.items
            self.items[sid] = {"exp": now + self.ttl, "ip": ip, "calls": 0}
        return sid

    def charge(self, sid, n: int, cap: int) -> str | None:
        """None when the session is valid and has room for n more calls (and counts them); else "unknown" or "cap"."""
        with self.lock:
            v = self.items.get(sid) if isinstance(sid, str) else None
            if not v or v["exp"] < time.monotonic():
                return "unknown"
            if v["calls"] + n > cap:
                return "cap"
            v["calls"] += n
            return None


def done_text(ctx: TurnContext, act: dict) -> str:
    t = act["type"]
    if t == "navigate":
        here = ctx._targets_here()
        names = ", ".join(x["id"] for x in (here or [])[:40])
        return f"Opened {act['path']}." + (f" Targets there: {names}." if names else "")
    if t == "highlight":
        return f"{act['target']} is in the spotlight now."
    if t == "scroll_to":
        return f"{act['target']} is in view now."
    if t == "click":
        return f"Pressed {act['target']}."
    if t == "fill":
        return f"{act['target']} is set to {act['value']!r}."
    return "Done."


def run_calls(calls, manifest: dict, registry: Registry, s: config.Settings, extra: dict | None = None) -> list[dict]:
    """The model's tool calls of one message, in order: UI calls validated (the browser runs them), data calls run here."""
    ctx = TurnContext(manifest, extra=extra or {})
    out = []
    for c in calls:
        cid = str(c.get("id") or "")[:120] if isinstance(c, dict) else ""
        name = c.get("name") if isinstance(c, dict) else None
        args = c.get("args") if isinstance(c, dict) and isinstance(c.get("args"), dict) else {}
        if not isinstance(name, str):
            out.append({"id": cid, "name": "", "ok": False, "output": "A tool call needs a name.", "action": None})
        elif name in UI_TOOL_NAMES:
            act, why = ctx.check(name, args, s.max_actions)
            out.append({"id": cid, "name": name, "ok": act is not None, "output": done_text(ctx, act) if act else why, "action": act})
        elif registry.has(name):
            body, ok = registry.run(name, args, ctx)
            out.append({"id": cid, "name": name, "ok": ok, "output": body, "action": None})
        else:
            out.append({"id": cid, "name": name[:64], "ok": False, "output": f"There is no tool called {name[:64]}.", "action": None})
    return out
