"""The chat's three tools. They call the real chain: decide -> (waiting run | post_decision) -> broker -> Yext -> learn."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .. import chain, store
from ..schema import Decision, Reason, Span, Suggestion
from . import feed as F
from .util import hours_text, is_pending, validate_hours

log = logging.getLogger("kaiku.chat.actions")
_locks: dict[str, asyncio.Lock] = {}


def _spans(h):
    return None if h in (None, "closed") else [Span(**x) for x in h]


def materialize(business_id: str, item: dict) -> Suggestion:
    """The stored Suggestion for a feed item. Feed items without one (the stub's 'stub-<date>') are saved first."""
    s = store.get_suggestion(item["id"])
    if s is not None:
        return s
    prop = item.get("proposed")
    s = Suggestion(
        id=item["id"], business_id=business_id, holiday_date=item.get("holiday_date") or item["id"][-10:],
        kind="closed" if prop == "closed" else ("hours" if prop else "no_change"), proposed=_spans(prop),
        confidence=float(item.get("confidence") or 0.5),
        reasons=[Reason(source=r.get("source", "feed"), text_fi=r.get("text_en", ""), text_en=r.get("text_en", ""))
                 for r in item.get("reasons", [])] or [Reason(source="feed", text_fi="", text_en=item.get("text_en", ""))],
        message_en=item.get("text_en", ""), status="sent", holiday_name_en=item.get("holiday_name_en"),
        holiday_name_fi=item.get("holiday_name_en"), last_year_hours=_spans(item.get("last_year")) or item.get("last_year"))
    store.save_suggestion(s)
    return s


def _apply_event(sid: str) -> dict:
    for e in reversed(store.recent_events(60)):
        if e.suggestion_id == sid and e.step == "apply":
            return e.detail or {}
    return {}


async def _decide_one(business_id: str, item: dict, action: str, edited, via: str = "web") -> dict:
    s = materialize(business_id, item)
    b = store.get_business(business_id)
    dec = Decision(suggestion_id=s.id, action=action, edited=edited if action == "edit" else None, via=via)
    async with _locks.setdefault(s.id, asyncio.Lock()):
        s = store.get_suggestion(s.id) or s
        if s.status in ("approved", "edited", "declined", "applied"):
            return {"ok": False, "error": "already decided"}
        resolved = False
        try:
            resolved = bool(await chain.on_decision(dec.model_dump(mode="json")))  # a chain run is waiting: it carries on itself
        except Exception as exc:
            log.warning("on_decision: %s", exc)
        if resolved:
            for _ in range(75):  # up to ~15 s for the waiting run to finish apply (status "applied") or the decline
                await asyncio.sleep(0.2)
                cur = store.get_suggestion(s.id)
                if cur and (cur.status in ("applied", "declined") or _apply_event(s.id).get("yext_status", "ok") != "ok"):
                    break
        else:
            await chain.post_decision(b, s, dec)
        cur = store.get_suggestion(s.id) or s
    det = _apply_event(s.id) if action != "decline" else {}
    return {"ok": True, "status": cur.status, "yext": det.get("yext_status"), "verified": bool(det.get("verified")),
            "hours": hours_text(det.get("hours")) if det.get("hours") else None}


async def decide(business_id: str, suggestion_id: str, action: str, edited_hours=None, via: str = "web") -> dict:
    item = F.find(business_id, suggestion_id)
    if item is None:
        return {"ok": False, "error": "unknown suggestion"}
    if item["kind"] == "no_change":
        return {"ok": False, "error": "nothing to decide, this one needs no change"}
    if not is_pending(item):
        return {"ok": False, "error": f"already {item.get('status')}"}
    if action not in ("approve", "edit", "decline"):
        return {"ok": False, "error": "action must be approve, edit or decline"}
    if action == "approve" and not item.get("proposed"):
        return {"ok": False, "needs_hours": True, "error": "this suggestion has no hours to approve; ask the owner which hours they want"}
    edited = None
    if action == "edit":
        edited = validate_hours(edited_hours)
        if edited is None:
            return {"ok": False, "error": "edited_hours must be 'closed' or [{start:'HH:MM',end:'HH:MM'}] with start before end"}
    members = item.get("members") or [None]
    results = []
    for m in members:
        sub = item if m is None else (F.find(business_id, m) or {**item, "id": m, "members": None})
        sub = {**sub, "members": None}
        results.append(await _decide_one(business_id, sub, action, edited, via))
    ok = all(r.get("ok") for r in results)
    first = next((r for r in results if r.get("ok")), results[0])
    out = {**first, "ok": ok, "suggestion_id": suggestion_id, "action": action,
           "final_hours": hours_text(edited) if action == "edit" else (hours_text(item.get("proposed")) if action == "approve" else None)}
    if ok and action in ("approve", "edit") and item["kind"] in ("holiday_hours", "period", "conflict"):
        out["follow_up_question"] = follow_up(item, out["final_hours"])
    return out


def follow_up(item: dict, final: str) -> str:
    name = item.get("holiday_name_en") or item.get("title_en") or "this holiday"
    ly = item.get("last_year")
    lyt = hours_text(ly) if ly else ""
    if lyt and lyt == final:
        return f"Last year {lyt}, this year {final} again. Want me to do this every {name}?"
    if lyt:
        return f"This year {final}, last year {lyt}. Want me to use {final} every {name}?"
    return f"Want me to do this every {name}?"


async def set_standing_permission(business_id: str, suggestion_id: str, enabled: bool, via: str = "web") -> dict:
    item = F.find(business_id, suggestion_id)
    if item is None:
        return {"ok": False, "error": "unknown suggestion"}
    if not enabled:
        return {"ok": True, "standing_permission": False}
    from ..learn import prefs
    sid = (item.get("members") or [item["id"]])[0]
    s = store.get_suggestion(sid) or materialize(business_id, item)
    p = await asyncio.to_thread(prefs.record_decision, business_id, chain._s_dict(s),
                                {"action": "approve", "standing_permission": True, "scope": "same",
                                 "via": via, "at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "standing_permission": bool(p.get("standing_permission"))}
