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


TEXT_KINDS = ("description", "review")
TEXT_DATE = "1970-01-01"   # stored text suggestions never share a date with a holiday card


def _ev(step, business_id, sid, fi, en, **detail):
    from .. import events
    from ..schema import Event
    return events.emit(Event(step=step, business_id=business_id, suggestion_id=sid, title_fi=fi, title_en=en, detail=detail))


def materialize_text(business_id: str, item: dict) -> Suggestion:
    """Description and review cards are stored as suggestions (kind 'ask') so with_decisions can read their status."""
    s = store.get_suggestion(item["id"])
    if s is not None:
        return s
    s = Suggestion(id=item["id"], business_id=business_id, holiday_date=TEXT_DATE, kind="ask", proposed=None,
                   confidence=float(item.get("confidence") or 0.5),
                   reasons=[Reason(source=r.get("source", "feed"), dataset_id=r.get("dataset_id", ""),
                                   text_fi=r.get("text_fi", ""), text_en=r.get("text_en", "")) for r in item.get("reasons", [])]
                   or [Reason(source="feed", text_fi="", text_en=item.get("text_en", ""))],
                   message_en=item.get("text_en", ""), message_fi=item.get("text_fi", ""), status="sent")
    store.save_suggestion(s)
    return s


def _log_decline(business_id: str, item: dict) -> None:
    import json
    from ..apply.yext import DATA_DIR
    import os
    from pathlib import Path
    p = Path(os.environ.get("KAIKU_DECLINES_FILE") or (DATA_DIR / "text_declines.jsonl"))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "business_id": business_id, "id": item["id"],
                                "kind": item["kind"], "proposed": item.get("proposed")}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _text_apply(item: dict, text: str, client=None) -> dict:
    from ..apply import yext as Y
    eid = item.get("entity_id") or chain.ENTITY
    if item["kind"] == "description":
        return Y.apply_description(eid, text, client)
    sample = any(r.get("source") == "sample_reviews" for r in item.get("reasons", []))
    return Y.apply_review_reply(eid, item.get("review_id") or item["id"].rsplit("-", 1)[-1], text, client, sample=sample)


async def _decide_text(business_id: str, item: dict, action: str, edited_text, via: str, client=None) -> dict:
    s = materialize_text(business_id, item)
    kind = item["kind"]
    text = None
    if action == "approve":
        text = item.get("proposed")
    elif action == "edit":
        text = edited_text.strip() if isinstance(edited_text, str) else None
    if action != "decline" and not (isinstance(text, str) and text.strip()):
        return {"ok": False, "needs_text": True, "error": "I need the exact text you want, send it as your own wording"}
    async with _locks.setdefault(s.id, asyncio.Lock()):
        s = store.get_suggestion(s.id) or s
        if s.status in ("approved", "edited", "declined", "applied"):
            return {"ok": False, "error": "already decided"}
        dec = Decision(suggestion_id=s.id, action=action, via=via)
        s.status = {"approve": "approved", "edit": "edited", "decline": "declined"}[action]
        store.save_suggestion(s)
        store.save_decision(dec)
        what_fi, what_en = ("kuvaus", "description") if kind == "description" else ("vastaus arvosteluun", "review reply")
        _ev("decide", business_id, s.id, f"Päätös: {what_fi} {dict(approve='hyväksytty', edit='muokattu', decline='hylätty')[action]}",
            f"Decision on the {what_en}: {action}", phase="decided", action=action, via=via)
        result: dict = {}
        if action != "decline":
            out = await asyncio.to_thread(_text_apply, item, text, client)
            ok = out.get("yext_status") == "ok"
            if kind == "description":
                title_en = ("Description saved to Yext, read back and verified" if ok and out.get("verified")
                            else "Description written to Yext" if ok else "Yext write failed")
                title_fi = ("Kuvaus tallennettu Yextiin, luettu takaisin ja varmistettu" if ok and out.get("verified")
                            else "Kuvaus kirjoitettu Yextiin" if ok else "Yext-kirjoitus epäonnistui")
            elif out.get("posted"):
                title_en = "Reply posted to the review in Yext" + (", read back and verified" if out.get("verified") else "")
                title_fi = "Vastaus julkaistu arvostelulle Yextissä" + (", luettu takaisin" if out.get("verified") else "")
            else:
                title_en = "Reply stored; the sandbox key cannot post review comments" if ok else "Reply could not be stored"
                title_fi = "Vastaus tallennettu; hiekkalaatikon avain ei voi julkaista arvostelukommentteja" if ok else "Vastausta ei voitu tallentaa"
            if ok and (kind == "description" or out.get("posted")):
                s.status = "applied"
                store.save_suggestion(s)
            _ev("apply", business_id, s.id, title_fi, title_en, yext_status=out.get("yext_status"), verified=out.get("verified"),
                written=out.get("written"), entity=out.get("entity_id"), entity_version=out.get("entity_version"),
                environment="sandbox", posted=out.get("posted"), stored=out.get("stored"), post_error=out.get("post_error"),
                error=None if ok else out.get("yext_status"))
            result = {"yext": out.get("yext_status"), "verified": bool(out.get("verified")), "posted": bool(out.get("posted")),
                      "stored": bool(out.get("stored")), "final_text": text}
            if not ok:
                result["ok"] = False
                result["error"] = out.get("yext_status")
        else:
            _log_decline(business_id, item)
        _ev("learn", business_id, s.id, "Opittu: ehdotus hylättiin, ei ehdoteta samaa uudelleen" if action == "decline"
            else "Opittu: omistajan versio kirjattu", "Learned: suggestion declined, I will not propose the same again"
            if action == "decline" else "Learned: the owner's own wording is kept", action=action, kind=kind)
    return {"ok": True, "status": s.status, "suggestion_id": item["id"], "action": action, **result}


async def decide(business_id: str, suggestion_id: str, action: str, edited_hours=None, via: str = "web", edited_text=None, _client=None) -> dict:
    item = F.find(business_id, suggestion_id)
    if item is None:
        return {"ok": False, "error": "unknown suggestion"}
    if item["kind"] in TEXT_KINDS:
        if not is_pending(item):
            return {"ok": False, "error": f"already {item.get('status')}"}
        if action not in ("approve", "edit", "decline"):
            return {"ok": False, "error": "action must be approve, edit or decline"}
        return await _decide_text(business_id, item, action, edited_text if edited_text is not None else (edited_hours if isinstance(edited_hours, str) else None), via, _client)
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
    subs = None
    if item["kind"] == "period" and not item.get("members"):
        from . import flow
        subs = flow.undecided_members(business_id, item)   # a real period: one decision per date not yet decided
        if not subs:
            return {"ok": False, "error": "already decided"}
        members = [m["id"] for m in subs]
    results = []
    for n, m in enumerate(members):
        if subs is not None:
            sub = subs[n]
        else:
            sub = item if m is None else (F.find(business_id, m) or {**item, "id": m, "members": None})
        sub = {**sub, "members": None}
        results.append(await _decide_one(business_id, sub, action, edited, via))
    ok = all(r.get("ok") for r in results)
    first = next((r for r in results if r.get("ok")), results[0])
    out = {**first, "ok": ok, "suggestion_id": suggestion_id, "action": action, "count": len(results),
           "final_hours": hours_text(edited) if action == "edit" else (hours_text(item.get("proposed")) if action == "approve" else None)}
    if len(results) > 1:   # one failed write must show: yext is "ok" only when every date went through
        out["yext"] = "ok" if all(r.get("yext") == "ok" for r in results if r.get("ok")) else "failed"
    if ok and action in ("approve", "edit") and item["kind"] in ("holiday_hours", "period", "conflict") and has_last_year(business_id, item):
        out["follow_up_question"] = follow_up(item, out["final_hours"])
    return out


def has_last_year(business_id: str, item: dict) -> bool:
    from . import flow
    return flow.has_last_year(business_id, item)


def follow_up(item: dict, final: str) -> str:
    from . import flow
    return flow.RECURRING_Q


async def set_standing_permission(business_id: str, suggestion_id: str, enabled: bool, via: str = "web") -> dict:
    item = F.find(business_id, suggestion_id)
    if item is None:
        return {"ok": False, "error": "unknown suggestion"}
    if not enabled:
        return {"ok": True, "standing_permission": False}
    from ..learn import prefs
    if item["kind"] == "period" and not item.get("members"):
        from . import flow
        ms = flow.period_members(business_id, item)
        item = ms[0] if ms else item
    sid = (item.get("members") or [item["id"]])[0]
    s = store.get_suggestion(sid) or materialize(business_id, item)
    p = await asyncio.to_thread(prefs.record_decision, business_id, chain._s_dict(s),
                                {"action": "approve", "standing_permission": True, "scope": "same",
                                 "via": via, "at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "standing_permission": bool(p.get("standing_permission"))}
