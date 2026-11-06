"""The brain: a tool-use loop on the Anthropic API (claude-sonnet-5-5), max 6 steps. Returns {text, actions}.

Actions are derived from the tools that ran (server-side), never typed by the model, so the browser only ever gets
known shapes: navigate {url}, spotlight {selector}, run_chain {...}.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from .tools import Tools

log = logging.getLogger("kaiku.voice.brain")
MODEL = "claude-sonnet-5-5"
MAX_STEPS = 6

SYSTEM = """You are Kaiku, the calm Finnish local-info assistant of Kaiku, a service that keeps a business's holiday opening hours right on Google, Apple Maps and directories. You speak out loud to a business owner or a judge watching a demo.

Rules:
- Answer in the language the user spoke (Finnish or English), in at most two short sentences, HARD LIMIT 30 words in total, plain text, no lists, no markdown, no emoji. Never use dashes as punctuation; write hours like "9-13" and dates like "24.12." (Finnish) or "24 December" (English), never as 2026-12-24. In Finnish say "aukioloajat" for opening hours.
- Call all the tools you need in one step, in parallel. Use the tools to look things up. Never invent data: every hour, date and number you say must come from a tool result. If a tool returns nothing or an error, say "I do not know" (in Finnish: "En tiedä") and what you checked.
- Never state what Google shows unless the suggestion's google_now.status is "verified"; otherwise say it has not been checked. Never say hours are "already applied" unless the suggestion's status is "applied". Keep every answer to at most 30 words. If a tool returns nothing, say so.
- You propose, you never decide. Hours only change when the business owner approves; say so when relevant. You cannot approve or apply anything.
- "What is wrong with <business>": call get_business and get_suggestions, then name the concrete problem, for example the holiday where Google still shows regular hours but last year the business had different hours, and what Kaiku suggests.
- "Run the chain for <holiday>": call run_chain with the holiday's date from get_business or the calendar (Christmas Eve 2026 is 2026-12-24), then say it is running and that the owner will be asked.
- "Travel to <date>": call timetravel with the date as YYYY-MM-DD (year 2026 unless said), then say what Kaiku will detect from the result. If the holiday is not a public holiday and the business is closed that weekday, say Kaiku will conclude no change is needed.
- The default business is furry-paw (Furry Paw Vet Clinic, Vantaa, a fictional sample business).
- Broker tools (if present) read the FIWARE NGSI-LD context broker; propose_update only writes a proposal."""


def _client():
    import anthropic
    return anthropic.AsyncAnthropic(max_retries=1, timeout=45.0)


async def _create(client, **kw):
    try:
        return await client.messages.create(**kw, thinking={"type": "between_tools"}, output_config={"effort": "low"})
    except Exception as e:  # noqa: BLE001 - an SDK/API that rejects the speed knobs still answers
        if type(e).__name__ not in ("BadRequestError", "TypeError"):
            raise
        log.info("retry without speed knobs: %s", type(e).__name__)
        return await client.messages.create(**kw)


def _merge_actions(raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    nav = next((a for a in raw if a["type"] == "navigate"), None)
    if nav:
        out.append(nav)
    out += [a for a in raw if a["type"] == "run_chain"][-1:]
    spot = [a for a in raw if a["type"] == "spotlight"]
    # the last spotlight wins, except that a run_chain keeps the event strip in view
    if spot:
        out.append(spot[-1])
    return out


MAX_WORDS = 30


def cap_words(text: str, limit: int = MAX_WORDS) -> str:
    """Server-side guarantee for the 30-word rule: cut at the last sentence end inside the limit, else at the limit."""
    words = text.split()
    if len(words) <= limit:
        return text
    head = " ".join(words[:limit])
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if head[-1:] in ".!?":
        return head
    if cut >= 10:
        return head[:cut + 1]
    return head.rstrip(",;:- ") + "."


async def ask(text: str, page: str = "/", lang: str = "auto", history: list[dict] | None = None,
              client: Any = None, tools: Tools | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        return {"text": "", "actions": [], "tools": [], "steps": 0}
    tools = tools or Tools()
    client = client or _client()
    msgs: list[dict] = []
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("text"), str) and h["text"].strip():
            msgs.append({"role": h["role"], "content": h["text"][:600]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": text[:800]})
    system = SYSTEM + f"\nThe user is looking at the page {page[:60]}. Language hint: {lang if lang in ('fi', 'en') else 'detect from the user words'}."
    raw_actions: list[dict] = []
    used: list[str] = []
    final = ""
    steps = 0
    for steps in range(1, MAX_STEPS + 1):
        resp = await _create(client, model=MODEL, max_tokens=700, system=system, tools=tools.specs(), messages=msgs)
        msgs.append({"role": "assistant", "content": resp.content})
        calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            final = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
            break
        results = []
        for c in calls:
            used.append(c.name)
            out = await tools.call(c.name, c.input if isinstance(c.input, dict) else {})
            raw_actions += out.pop("_actions", []) if isinstance(out, dict) else []
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out, ensure_ascii=False)[:6000],
                            **({"is_error": True} if isinstance(out, dict) and "error" in out else {})})
        msgs.append({"role": "user", "content": results})
    else:
        final = ""
    if not final:
        final = "En tiedä." if lang == "fi" else "I do not know."
    final = cap_words(final)
    return {"text": final, "actions": _merge_actions(raw_actions), "tools": used, "steps": steps}
