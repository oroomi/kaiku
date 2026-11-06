"""Owner chat routes: GET /api/chat/open, POST /api/chat, and the keyed drawer fragment."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import events, store
from . import brain
from . import feed as F
from .util import hours_text, is_pending

router = APIRouter()
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
    body = f"{title}. {text}".strip(". ") + "." if text and not text.startswith(title) else (text or title)
    if i["kind"] != "no_change" and is_pending(i) and i.get("proposed") and "suggest" not in body.lower():
        body += f" I suggest {hours_text(i['proposed'])}."
    return {"role": "kaiku", "kind": "note" if i["kind"] == "no_change" else "suggestion", "suggestion_id": i["id"],
            "item_kind": i["kind"], "holiday_date": i.get("holiday_date"), "text": body.replace("..", "."), "status": i.get("status", "proposed"),
            "proposed": (f"{len(i['proposed'])} dates" if i["kind"] == "period" and isinstance(i.get("proposed"), list) and i["proposed"]
                         and isinstance(i["proposed"][0], dict) and "date" in i["proposed"][0] else hours_text(i.get("proposed")) or None)}


def opening(business_id: str, sess_id: str = "default") -> list[dict]:
    b = store.get_business(business_id)
    if b is None:
        raise HTTPException(404, "unknown business")
    items = F.get_feed(business_id).get("suggestions", [])
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
def chat_open(business: str = "furry-paw", session: str = "default"):
    return {"business_id": business, "messages": opening(business, session)}


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
