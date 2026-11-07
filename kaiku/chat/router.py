"""Owner chat routes: GET /api/chat/open, POST /api/chat, and the keyed drawer fragment."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import events, store
from . import actions as A
from . import brain
from . import feed as F
from . import flow
from .util import hours_text, is_pending

router = APIRouter()
log = logging.getLogger("kaiku.chat.router")
_sessions: dict[str, dict] = {}
MAX_MSG = 400


def _sess_path():
    from ..contact import whatsapp as W  # type: ignore
    return W.data_dir() / "chat_sessions.json"


def _load_sessions() -> None:
    try:
        d = json.loads(_sess_path().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            _sessions.update(d)
    except Exception:
        pass


def persist() -> None:
    """Chat memory survives a restart: a WhatsApp thread spans minutes and the service restarts on every deploy."""
    try:
        _sess_path().write_text(json.dumps(_sessions, default=str), encoding="utf-8")
    except Exception as e:  # pragma: no cover
        log.warning("chat sessions not saved: %s", e)


_load_sessions()


def session(sid: str) -> dict:
    s = _sessions.setdefault(sid or "default", {"hist": [], "log": [], "focus": None, "followup": None, "stage": None, "pending": None, "t": time.time()})
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
def chat_open(business: str = "furry-paw", session: str = "default", quick: int = 0, full: int = 0):
    """The page's chat opens EMPTY: only what this session already said. full=1 returns Kaiku's old opening too
    (intro + one line per suggestion), which WhatsApp and API callers use through opening()."""
    if store.get_business(business) is None:
        raise HTTPException(404, "unknown business")
    if full:
        return {"business_id": business, "messages": opening(business, session, network=not quick)}
    return {"business_id": business, "messages": list(session_of(session)["log"]), "focus": session_of(session).get("focus")}


def session_of(sid: str) -> dict:
    return session(sid)


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
    if not f:
        s["stage"] = None
    statuses = {i["id"]: i.get("status", "proposed") for i in items}
    return {"reply": reply, "actions": acts, "statuses": statuses, "focus": s["focus"]}


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


ContextIn = AcceptIn


def _item_or_404(body: AcceptIn, suggestion_id: str) -> dict:
    if store.get_business(body.business_id) is None:
        raise HTTPException(404, "unknown business")
    item = F.find(body.business_id, suggestion_id)
    if item is None:
        raise HTTPException(404, "unknown suggestion")
    return item


@router.post("/api/suggestions/{suggestion_id}/accept")
async def accept(suggestion_id: str, body: AcceptIn | None = None):
    """Accept = one tap: the suggestion is applied through actions.decide at once; Kaiku's receipt, the recurring question
    (when there is last-year data) and the hand-off to the next item go into the chat."""
    body = body or AcceptIn()
    item = _item_or_404(body, suggestion_id)
    s = session(body.session)
    s["t"] = time.time()
    if item["kind"] == "no_change" or not is_pending(item):
        return {"ok": False, "error": f"already {item.get('status')}" if item["kind"] != "no_change" else "nothing to decide",
                "reply": "That one is already decided." if item["kind"] != "no_change" else "That one needs no change.", "status": item.get("status"), "actions": []}
    from .brain import Turn  # one tap = approve now (owner's rule 7 Nov); Kaiku's receipt, the recurring question and the next item follow in the chat
    turn = Turn(body.business_id, s)
    s["focus"], s["stage"], s["pending"], s["followup"] = item["id"], None, None, None
    reply = await flow.apply_and_say(turn, body.business_id, s, item, "approve")
    s["log"].append({"role": "kaiku", "kind": "chat", "text": reply})
    s["hist"] += [("user", f"(accepted on the card: {item.get('title_en', suggestion_id)})"), ("assistant", reply)]
    _listing_changed(body.business_id)
    return {"ok": True, "reply": reply, "focus": s.get("focus"), "stage": s.get("stage"), "actions": turn.actions}


@router.post("/api/suggestions/{suggestion_id}/discard")
async def discard(suggestion_id: str, body: AcceptIn | None = None):
    """Discard: the same decide path as a 'no' (action decline, via web, a learn event). Kaiku writes one line."""
    body = body or AcceptIn()
    item = _item_or_404(body, suggestion_id)
    s = session(body.session)
    s["t"] = time.time()
    if item["kind"] == "no_change" or not is_pending(item):
        return {"ok": False, "error": "nothing to discard", "reply": "That one is already decided.", "status": item.get("status"), "actions": []}
    try:
        r = await A.decide(body.business_id, item["id"], "decline", via="web")
    except Exception as exc:
        log.warning("discard %s: %s", suggestion_id, type(exc).__name__)
        r = {"ok": False, "error": "could not discard"}
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error"), "reply": brain.EN["error"], "status": item.get("status"), "actions": []}
    line = flow.discard_text(item)
    if s.get("focus") == item["id"]:
        flow.reset(s)
    s["log"].append({"role": "kaiku", "kind": "chat", "text": line})
    s["hist"] += [("user", f"(discarded on the card: {item.get('title_en', suggestion_id)})"), ("assistant", line)]
    return {"ok": True, "reply": line, "status": r.get("status"),
            "actions": [{"type": "decided", "suggestion_id": item["id"], "action": "decline", "status": r.get("status")}]}


@router.post("/api/suggestions/{suggestion_id}/change")
def suggest_change(suggestion_id: str, body: AcceptIn | None = None):
    """'Suggest a change' hands over too: Kaiku says what he suggested and why, and asks what it should be."""
    body = body or AcceptIn()
    item = F.find(body.business_id, suggestion_id)
    if item is None:
        raise HTTPException(404, "unknown suggestion")
    if item["kind"] == "no_change" or not is_pending(item):
        raise HTTPException(409, "nothing to change on this one")
    s = session(body.session)
    s["t"] = time.time()
    line = flow.start_change(s, item)
    s["log"].append({"role": "kaiku", "kind": "chat", "text": line})
    s["hist"] += [("user", f"(wants to change: {item.get('title_en')})"), ("assistant", line)]
    return {"ok": True, "reply": line, "focus": item["id"]}
