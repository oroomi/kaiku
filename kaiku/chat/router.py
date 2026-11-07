"""Owner chat routes: GET /api/chat/open, POST /api/chat, and the keyed drawer fragment."""
from __future__ import annotations

import logging
import re
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import events, store
from . import actions as A
from . import brain
from . import feed as F
from .util import hours_text, is_pending

router = APIRouter()
log = logging.getLogger("kaiku.chat.router")
_sessions: dict[str, dict] = {}
MAX_MSG = 400


def session(sid: str) -> dict:
    s = _sessions.setdefault(sid or "default", {"hist": [], "log": [], "focus": None, "followup": None, "t": time.time()})
    if len(_sessions) > 200:  # demo-sized housekeeping
        for k in sorted(_sessions, key=lambda k: _sessions[k]["t"])[:50]:
            _sessions.pop(k, None)
    return s


class ChatIn(BaseModel):
    business_id: str = "furry-paw"
    message: str
    session: str = "default"


def _bubble(i: dict) -> dict:
    text = i.get("text_en") or ""
    title = i.get("title_en") or ""
    body = f"{title}. {text}".strip(". ") if text and not text.startswith(title) else (text or title)
    body = body if body.endswith(("?", "!", ".")) else body + "."
    if i["kind"] != "no_change" and is_pending(i) and i.get("proposed") and "suggest" not in body.lower():
        body += f" I suggest {hours_text(i['proposed'])}."
    return {"role": "kaiku", "kind": "note" if i["kind"] == "no_change" else "suggestion", "suggestion_id": i["id"],
            "item_kind": i["kind"], "holiday_date": i.get("holiday_date"), "text": body.replace("..", "."), "status": i.get("status", "proposed"),
            "proposed": (f"{len(i['proposed'])} dates" if i["kind"] == "period" and isinstance(i.get("proposed"), list) and i["proposed"]
                         and isinstance(i["proposed"][0], dict) and "date" in i["proposed"][0] else hours_text(i.get("proposed")) or None)}


def opening(business_id: str, sess_id: str = "default", network: bool = True) -> list[dict]:
    b = store.get_business(business_id)
    if b is None:
        raise HTTPException(404, "unknown business")
    items = F.get_feed(business_id, network).get("suggestions", [])
    act = [i for i in items if i["kind"] != "no_change"]
    notes = [i for i in items if i["kind"] == "no_change"]
    fi = getattr(b, "owner_language", "en") == "fi"
    waiting = [i for i in act if is_pending(i)]
    if fi:
        intro = f"Hei {b.name}. " + (f"Huomasin {len(waiting)} asiaa." if waiting else "Mikään ei vaadi muutosta juuri nyt.")
    elif waiting:
        intro = f"Hi {b.name}. I noticed {len(waiting)} thing{'s' if len(waiting) != 1 else ''}."
    elif act:
        intro = f"Hi {b.name}. Everything is handled, nothing is waiting for you."
    else:
        intro = f"Hi {b.name}. I checked your hours and there is nothing to change."
    msgs = [{"role": "kaiku", "kind": "intro", "text": intro}]
    msgs += [_bubble(i) for i in act]
    msgs += [_bubble(i) for i in notes]
    s = session(sess_id)
    msgs += s["log"]
    return msgs


@router.get("/api/chat/open")
def chat_open(business: str = "furry-paw", session: str = "default", quick: int = 0):
    return {"business_id": business, "messages": opening(business, session, network=not quick)}


@router.post("/api/chat")
async def chat(body: ChatIn):
    msg = (body.message or "").strip()[:MAX_MSG]
    if not msg:
        raise HTTPException(422, "empty message")
    if store.get_business(body.business_id) is None:
        raise HTTPException(404, "unknown business")
    s = session(body.session)
    s["t"] = time.time()
    reply, acts = await brain.respond(body.business_id, s, msg)
    if any(a.get("type") == "decided" for a in acts):
        _listing_changed(body.business_id)
    s["hist"] += [("user", msg), ("assistant", reply)]
    s["log"] += [{"role": "user", "kind": "chat", "text": msg}, {"role": "kaiku", "kind": "chat", "text": reply}]
    items = F.get_feed(body.business_id).get("suggestions", [])
    f = brain.focus_of(items, s)
    s["focus"] = f["id"] if f else None
    statuses = {i["id"]: i.get("status", "proposed") for i in items}
    return {"reply": reply, "actions": acts, "statuses": statuses}


@router.get("/api/chat/keyed")
def chat_keyed(request: Request):
    return {"keyed": events.has_key(request)}


def _listing_changed(business_id: str) -> None:
    """A decision may have written to Yext: the next listing and score read must not come from the 30 s cache."""
    try:
        from ..listing import router as L
        L.invalidate(business_id)
    except Exception:
        pass


class AcceptIn(BaseModel):
    business_id: str = "furry-paw"
    session: str = "default"


@router.post("/api/suggestions/{suggestion_id}/accept")
async def accept(suggestion_id: str, body: AcceptIn | None = None):
    """One click on a card: the very same decide(...) path the chat uses, action approve, via web.
    Kaiku's confirmation and the standing-permission question go into the chat session so the next 'yes' answers it."""
    body = body or AcceptIn()
    if store.get_business(body.business_id) is None:
        raise HTTPException(404, "unknown business")
    item = F.find(body.business_id, suggestion_id)
    try:
        r = await A.decide(body.business_id, suggestion_id, "approve", via="web")
    except Exception as exc:  # a card kind the chain cannot apply yet must not 500 the page
        log.warning("accept %s: %s", suggestion_id, type(exc).__name__)
        r = {"ok": False, "error": "could not apply"}
    _listing_changed(body.business_id)
    s = session(body.session)
    s["t"] = time.time()
    if not r.get("ok"):
        reply = brain.EN["error"]
        if r.get("needs_hours"):
            reply = "I have no ready text for that one yet. Tell me what it should say."
        elif str(r.get("error", "")).startswith("already"):
            reply = "That one is already decided."
        return {"ok": False, "error": r.get("error"), "reply": reply, "status": (item or {}).get("status"), "actions": []}
    what = f"{(item or {}).get('holiday_name_en') or (item or {}).get('title_en') or 'that'} {r.get('final_hours') or ''}".strip()
    fu = re.sub(r" \d{1,2}\.\d{1,2}\.(?=[?.])", "", r.get("follow_up_question") or "")   # "every Christmas Eve 24.12.?" reads as "every Christmas Eve?"
    reply = (brain.EN["saved"].format(what=what) + " " + fu).strip()
    s["followup"] = suggestion_id if r.get("follow_up_question") else None
    s["focus"] = None
    s["log"].append({"role": "kaiku", "kind": "chat", "text": reply})
    s["hist"] += [("user", f"(accepted on the card: {(item or {}).get('title_en', suggestion_id)})"), ("assistant", reply)]
    return {"ok": True, "reply": reply, "status": r.get("status"), "yext": r.get("yext"), "verified": r.get("verified"),
            "actions": [{"type": "decided", "suggestion_id": suggestion_id, "action": "approve", "status": r.get("status")}]}


class ContextIn(BaseModel):
    business_id: str = "furry-paw"
    session: str = "default"


@router.post("/api/suggestions/{suggestion_id}/change")
def suggest_change(suggestion_id: str, body: ContextIn | None = None):
    """'Suggest a change' on a card: that suggestion becomes the chat's current context, so the owner's next message
    ('make it 10-14', 'closed') is decided against it. Kaiku's line goes into the session log."""
    body = body or ContextIn()
    item = F.find(body.business_id, suggestion_id)
    if item is None:
        raise HTTPException(404, "unknown suggestion")
    if item["kind"] == "no_change" or not is_pending(item):
        raise HTTPException(409, "nothing to change on this one")
    s = session(body.session)
    s["t"] = time.time()
    s["focus"] = item["id"]
    s["followup"] = None
    line = (f"You want to change {item.get('title_en') or 'this'}. Tell me the new hours, or what is wrong, "
            "by text or by holding space to talk.")
    s["log"].append({"role": "kaiku", "kind": "chat", "text": line})
    s["hist"] += [("user", f"(wants to change: {item.get('title_en')})"), ("assistant", line)]
    return {"ok": True, "reply": line, "focus": item["id"]}
