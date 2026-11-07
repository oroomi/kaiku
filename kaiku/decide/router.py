"""Owner phone page /d/<token> and its JSON API. English by default, Finnish when the business owner_language is fi."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Literal, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .. import chain, events, store
from ..contact import messages as M
from . import step, tokens

router = APIRouter()
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FI_ACTION = {"approve": "hyväksy", "edit": "muokkasi", "decline": "ei kiitos"}
EN_ACTION = {"approve": "approved", "edit": "edited", "decline": "declined"}
EN_WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FI_WD = ["maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina", "sunnuntaina"]
EXPIRED_FI = "Ehdotus vanheni ennen päätöstä. Kaiku lähettää uuden ehdotuksen."
EXPIRED_EN = "The suggestion expired before a decision. Kaiku will send a new suggestion."


class Span(BaseModel):
    start: str
    end: str


class DecideBody(BaseModel):
    action: Literal["approve", "edit", "decline"]
    edited: Union[list[Span], Literal["closed"], None] = None
    reason_chip: Optional[str] = None
    standing_permission: bool = False
    scope: Literal["same", "all"] = "same"


def _hh(t: str) -> str:
    h, m = t.split(":")
    return str(int(h)) if m == "00" else f"{int(h)}:{m}"


def spans_fi(spans) -> str:
    if spans == "closed" or not spans:
        return "suljettu"
    return ", ".join(f"{_hh(s['start'])}-{_hh(s['end'])}" for s in spans)


def _holiday(iso: str) -> dict:
    name_fi, name_en, ess = None, None, None
    try:
        from ..detect import holidays
        h = holidays.get(iso)
        if h:
            name_fi, name_en = h.name_fi, h.name_en
    except Exception:
        pass
    ch = chain.HOLIDAYS.get(iso[5:])
    if ch:
        name_fi, name_en, ess = name_fi or ch[0], name_en or ch[1], ch[2]
    d = date.fromisoformat(iso)
    return {"name_fi": name_fi or "Pyhäpäivä", "name_en": name_en or "Holiday",
            "essive": ess or FI_WD[d.weekday()], "date_fi": f"{d.day}.{d.month}.", "weekday_en": EN_WD[d.weekday()]}


def view_for(token: str, rec: dict) -> dict:
    s = store.get_suggestion(rec["suggestion_id"])
    b = store.get_business(rec["business_id"])
    if not s or not b:
        raise HTTPException(404, "suggestion not found")
    h = _holiday(s.holiday_date)
    sp = [x.model_dump() for x in s.proposed] if s.proposed else None
    lang = M.owner_lang(b)
    when = f"{h['essive'].capitalize()} {h['date_fi']}"
    when_en = f"{h['weekday_en']} {h['date_fi']}"
    if s.kind == "hours" and sp:
        sentence = f"{when} auki klo {spans_fi(sp)}"
        en = f"{h['name_en']}, {when_en}: open {spans_fi(sp)}"
    elif s.kind == "closed":
        sentence = f"{when} suljettu"
        en = f"{h['name_en']}, {when_en}: closed"
    else:
        sentence = f"{when} ei muutosta aukioloaikoihin"
        en = f"{h['name_en']}, {when_en}: no change to the hours"
    r = s.reasons[0] if s.reasons else None
    return {"token": token, "lang": lang, "suggestion_id": s.id, "business": {"id": b.id, "name": b.name, "address": b.address},
            "holiday": h, "kind": s.kind, "proposed": sp, "sentence_fi": sentence, "sentence_en": en,
            "reason_fi": r.text_fi if r else "", "reason_en": r.text_en if r else "",
            "suggestion_expired": s.status == "expired" and not rec["used"],
            "used": rec["used"], "expired": rec["expired"], "decision": rec.get("decision")}


def _page(request: Request, name: str, status: int = 200, **ctx):
    from ..app import render
    ctx.setdefault("lang", (ctx.get("v") or {}).get("lang") or M.owner_lang(None))
    resp = render(request, name, **ctx)
    resp.status_code = status
    return resp


@router.get("/d/{token}", response_class=HTMLResponse)
def decide_page(request: Request, token: str):
    rec = tokens.lookup(token)
    if not rec:
        return _page(request, "decide.html", 404, state="missing", v=None)
    try:
        v = view_for(token, rec)
    except HTTPException:
        return _page(request, "decide.html", 404, state="missing", v=None)
    state = "expired" if ((rec["expired"] or v["suggestion_expired"]) and not rec["used"]) else "done" if rec["used"] else "open"
    return _page(request, "decide.html", 200, state=state, v=v)


@router.get("/api/decide/{token}")
def decide_data(token: str):
    rec = tokens.lookup(token)
    if not rec:
        raise HTTPException(404, "unknown link")
    return view_for(token, rec)


def _validate(body: DecideBody) -> Optional[list[dict]] | str:
    if body.action != "edit":
        return None
    if body.edited is None:
        raise HTTPException(422, "edit needs edited hours or 'closed'")
    if body.edited == "closed":
        return "closed"
    if not body.edited:
        raise HTTPException(422, "edited is empty")
    out = []
    for sp in body.edited:
        if not (HHMM.match(sp.start) and HHMM.match(sp.end)):
            raise HTTPException(422, "times must be HH:MM")
        if sp.start >= sp.end:
            raise HTTPException(422, "start must be before end")
        out.append({"start": sp.start, "end": sp.end})
    return out


@router.post("/api/decide/{token}")
async def decide_post(token: str, body: DecideBody):
    rec = tokens.lookup(token)
    if not rec:
        raise HTTPException(404, "unknown link")
    if rec["expired"] and not rec["used"]:
        raise HTTPException(410, "link expired")
    sid = rec["suggestion_id"]
    sug = store.get_suggestion(sid)
    if not sug:
        return JSONResponse({"state": "missing", "message_fi": "Ehdotusta ei löydy.",
                             "message_en": "The suggestion cannot be found."}, status_code=404)
    edited = _validate(body)
    late = sug.status == "expired" and sid not in step.pending() and not rec["used"]
    decision = {"suggestion_id": sid, "action": body.action, "edited": edited,
                "reason_chip": body.reason_chip if body.action == "decline" else None,
                "standing_permission": bool(body.standing_permission) and body.action != "decline",
                "scope": body.scope, "via": "web", "at": datetime.now(timezone.utc).isoformat()}
    if late:
        # The decide step timed out: nothing waits. Never claim success unless the chain accepts it out of band.
        fn = getattr(chain, "on_decision", None)
        ok = False
        if fn:
            try:
                r = fn(decision)
                if hasattr(r, "__await__"):
                    r = await r
                ok = bool(r)
            except Exception:
                ok = False
        if not ok:
            return JSONResponse({"state": "expired", "message_fi": EXPIRED_FI, "message_en": EXPIRED_EN}, status_code=410)
        if not tokens.mark_used(token, decision):
            raise HTTPException(409, "already answered")
        return {"ok": True, "decision": decision, "waiting_chain": False, "late": True,
                "next": "skip" if body.action == "decline" else "apply"}
    if not tokens.mark_used(token, decision):
        raise HTTPException(409, "already answered")
    if step.resolve(sid, decision):
        waiting = True
    else:
        waiting = False
        s = store.get_suggestion(sid)
        events.emit(events.Event(step="decide", business_id=rec["business_id"], suggestion_id=sid,
                                 title_fi=f"Omistaja päätti: {FI_ACTION[body.action]}",
                                 title_en=f"Owner decided: {EN_ACTION[body.action]}",
                                 detail={"phase": "decided", "action": body.action, "via": "web", "decision": decision}))
        fn = getattr(chain, "on_decision", None)
        if fn:
            try:
                r = fn(decision)
                if hasattr(r, "__await__"):
                    await r
            except Exception:
                pass
    return {"ok": True, "decision": decision, "waiting_chain": waiting,
            "next": "skip" if body.action == "decline" else "apply"}


class ChannelBody(BaseModel):
    channel: Literal["email", "whatsapp", "call"]


@router.post("/api/decide/{token}/channel")
def decide_channel(token: str, body: ChannelBody):
    """The question after the receipt: how does the owner want to be reached next time? Same token as the decision; it is
    asked only once the decision is in (token used), and never after the link expired. Stored with the other prefs
    (kaiku.learn.prefs), read by the contact ladder."""
    from ..learn import prefs
    rec = tokens.lookup(token)
    if not rec:
        raise HTTPException(404, "unknown link")
    if rec["expired"]:
        raise HTTPException(410, "link expired")
    if not rec["used"]:
        raise HTTPException(409, "answer the suggestion first")
    b = store.get_business(rec["business_id"])
    prefs.set_contact_channel(rec["business_id"], body.channel, said=f"tapped {body.channel} on the decision page")
    lang = M.owner_lang(b)
    return {"ok": True, "channel": body.channel, "message": M.channel_confirm_text(body.channel, lang),
            "message_en": M.channel_confirm_text_en(body.channel), "message_fi": M.channel_confirm_text_fi(body.channel)}
