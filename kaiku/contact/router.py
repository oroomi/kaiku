"""WhatsApp webhook: verify handshake, inbound parsing (buttons, free text, statuses) -> Decision dicts."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from . import messages as M
from . import whatsapp as W

log = logging.getLogger(__name__)
router = APIRouter()
_lock = threading.RLock()


# ------------------------------------------------------------------ verify token

def ensure_verify_token() -> str:
    """Return WA_VERIFY_TOKEN; generate one and append it to .env when absent (never printed)."""
    W.load_env()
    tok = os.environ.get("WA_VERIFY_TOKEN")
    if tok:
        return tok
    tok = secrets.token_urlsafe(18)
    p = W.env_path()
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\nWA_VERIFY_TOKEN={tok}\n")
        os.chmod(p, 0o600)
    except OSError:
        pass
    os.environ["WA_VERIFY_TOKEN"] = tok
    return tok


# ------------------------------------------------------------------ context store (wa_context.json)

def _ctx_path():
    return W.data_dir() / "wa_context.json"


def _load() -> dict:
    try:
        d = json.loads(_ctx_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for k in ("messages", "latest", "awaiting_edit", "pending_buttons", "last_inbound", "decided", "business"):
        d.setdefault(k, {})
    d.setdefault("seen", [])
    return d


def _save(d: dict) -> None:
    d["seen"] = d["seen"][-300:]
    tmp = _ctx_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_ctx_path())


def register_sent(phone: str, suggestion_id: str, wa_message_id: str | None = None, business_id: str | None = None) -> None:
    """Remember which suggestion a WhatsApp message (and the phone's latest thread) belongs to."""
    ph = W.normalize_phone(phone)
    with _lock:
        d = _load()
        if wa_message_id:
            d["messages"][wa_message_id] = suggestion_id
        d["latest"][ph] = suggestion_id
        d["decided"].pop(suggestion_id, None)
        if business_id:
            d["business"][suggestion_id] = business_id
        _save(d)


def set_pending_buttons(phone: str, suggestion_id: str, body: str, buttons=None) -> None:
    with _lock:
        d = _load()
        d["pending_buttons"][W.normalize_phone(phone)] = {"suggestion_id": suggestion_id, "body": body,
                                                          "buttons": buttons or W.DEFAULT_BUTTONS}
        _save(d)


def has_window(phone: str) -> bool:
    """True when the phone wrote to us in the last 24 h (free-form messages allowed)."""
    t = _load()["last_inbound"].get(W.normalize_phone(phone))
    return bool(t) and time.time() - t < 24 * 3600


def is_decided(suggestion_id: str) -> bool:
    return suggestion_id in _load()["decided"]


# ------------------------------------------------------------------ free text

_APPROVE = {"ok", "okei", "kyllä", "kylla", "jees", "joo", "juu", "hyväksyn", "hyvä", "k", "yes", "kyl", "selvä", "sopii"}
_DECLINE = {"ei", "ei kiitos", "en", "ei muutosta", "no", "ei halua", "älä muuta", "ala muuta"}
_CLOSED = {"suljettu", "kiinni", "kiinni koko päivän", "ei auki", "olemme kiinni", "closed"}
_HOURS = re.compile(r"^(?:klo\.?\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|\u2013|\u2014|to|asti)\s*(?:klo\.?\s*)?(\d{1,2})(?:[:.](\d{2}))?$")


def _hhmm(h: str, m: str | None) -> str | None:
    h_i, m_i = int(h), int(m or 0)
    if not (0 <= h_i <= 24 and 0 <= m_i < 60):
        return None
    return f"{h_i:02d}:{m_i:02d}"


def parse_free_text(text: str) -> dict | None:
    """-> {'action':'approve'} | {'action':'decline'} | {'action':'edit','edited':'closed'|[{start,end}]} | None"""
    t = re.sub(r"[!.?,]+$", "", (text or "").strip().lower())
    t = re.sub(r"\s+", " ", t)
    if not t:
        return None
    if t in _CLOSED:
        return {"action": "edit", "edited": "closed"}
    if t in _APPROVE:
        return {"action": "approve"}
    if t in _DECLINE:
        return {"action": "decline"}
    m = _HOURS.match(t)
    if m:
        a, b = _hhmm(m[1], m[2]), _hhmm(m[3], m[4])
        if a and b and a < b:
            return {"action": "edit", "edited": [{"start": a, "end": b}]}
    return None


# ------------------------------------------------------------------ inbound parsing

def parse_inbound(payload: dict) -> list[dict]:
    """Flatten a Meta webhook body into items: kind in button|text|status|other."""
    items: list[dict] = []
    for entry in payload.get("entry", []) or []:
        for ch in entry.get("changes", []) or []:
            v = ch.get("value", {}) or {}
            for m in v.get("messages", []) or []:
                it = {"from": m.get("from"), "message_id": m.get("id"), "context_id": (m.get("context") or {}).get("id"),
                      "timestamp": m.get("timestamp")}
                typ = m.get("type")
                if typ == "interactive":
                    br = (m.get("interactive") or {}).get("button_reply") or (m.get("interactive") or {}).get("list_reply")
                    it.update(kind="button", button_id=(br or {}).get("id", ""), title=(br or {}).get("title", ""))
                elif typ == "button":  # quick reply of a template
                    it.update(kind="button", button_id=(m.get("button") or {}).get("payload", ""), title=(m.get("button") or {}).get("text", ""))
                elif typ == "text":
                    it.update(kind="text", text=(m.get("text") or {}).get("body", ""))
                else:
                    it.update(kind="other", type=typ)
                items.append(it)
            for st in v.get("statuses", []) or []:
                items.append({"kind": "status", "message_id": st.get("id"), "status": st.get("status"),
                              "to": st.get("recipient_id"), "errors": st.get("errors"), "timestamp": st.get("timestamp")})
    return items


def _split_button_id(bid: str) -> tuple[str, str | None]:
    a, _, sid = (bid or "").partition(":")
    return a.strip().lower(), (sid or None)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _known(d: dict, sid: str) -> bool:
    return (sid in d["decided"] or sid in d["business"] or sid in d["messages"].values()
            or sid in d["latest"].values() or sid in d["awaiting_edit"].values())


def make_decision(sid: str, action: str, edited=None, via: str = "whatsapp") -> dict:
    return {"suggestion_id": sid, "action": action, "edited": edited, "reason_chip": None,
            "standing_permission": False, "via": via, "at": _now()}


# ------------------------------------------------------------------ handling

def _emit(decision: dict, business_id: str | None) -> None:
    try:
        from kaiku import events  # type: ignore
    except ImportError:
        return
    try:
        a = decision["action"]
        fi = {"approve": "Omistaja hyväksyi ehdotuksen WhatsAppissa", "edit": "Omistaja muokkasi aukioloaikaa WhatsAppissa",
              "decline": "Omistaja kieltäytyi ehdotuksesta WhatsAppissa"}[a]
        en = {"approve": "Owner approved the suggestion on WhatsApp", "edit": "Owner edited the hours on WhatsApp",
              "decline": "Owner declined the suggestion on WhatsApp"}[a]
        events.emit(events.Event(ts=_now(), step="decide", business_id=business_id, suggestion_id=decision["suggestion_id"],
                                 title_fi=fi, title_en=en, detail={"decision": decision}))
    except Exception:
        pass


async def _forward(decision: dict) -> None:
    try:
        from kaiku import chain  # type: ignore
        fn = getattr(chain, "on_decision", None)
    except ImportError:
        return
    if not fn:
        return
    try:
        r = fn(decision)
        if inspect.isawaitable(r):
            await r
    except Exception:
        pass


async def handle_payload(payload: dict, client: W.WhatsAppClient | None = None) -> dict:
    """Process one webhook body. Returns {'decisions': [...], 'statuses': [...], 'ignored': n, 'replies': n}."""
    client = client or W.get_client()
    out = {"decisions": [], "statuses": [], "ignored": 0, "replies": 0, "edit_requested": [], "unknown": []}
    for it in parse_inbound(payload):
        if it["kind"] == "status":
            out["statuses"].append({k: it.get(k) for k in ("message_id", "status", "to", "errors")})
            continue
        phone = W.normalize_phone(it["from"])
        with _lock:
            d = _load()
            if it["message_id"] in d["seen"]:
                out["ignored"] += 1
                continue
            d["seen"].append(it["message_id"])
            d["last_inbound"][phone] = time.time()
            sid = d["messages"].get(it.get("context_id") or "") or d["latest"].get(phone)
            pend = d["pending_buttons"].pop(phone, None)
            _save(d)
        if it.get("message_id"):
            client.mark_read(it["message_id"])
        # A reply to the first-contact template reopens the window: now deliver the real message.
        if pend and it["kind"] == "text" and parse_free_text(it.get("text", "")) is None:
            r = client.send_buttons(phone, pend["body"], [tuple(b) for b in pend["buttons"]])
            if r.get("ok"):
                register_sent(phone, pend["suggestion_id"], r.get("message_id"))
            out["replies"] += 1
            continue
        if not sid:
            out["ignored"] += 1
            continue

        decision = None
        if it["kind"] == "button":
            act, bsid = _split_button_id(it.get("button_id", ""))
            sid = bsid or sid
            with _lock:
                known = _known(_load(), sid)
            if not known:
                log.warning("button %r for unknown suggestion %r from %s", it.get("button_id"), sid, phone)
                client.send_text(phone, M.unknown_suggestion_text()); out["replies"] += 1
                out["unknown"].append(sid)
                continue
            if act == "approve":
                decision = make_decision(sid, "approve")
            elif act == "decline":
                decision = make_decision(sid, "decline")
            elif act == "edit":
                with _lock:
                    d = _load(); d["awaiting_edit"][phone] = sid; _save(d)
                client.send_text(phone, M.edit_prompt_text()); out["replies"] += 1
                out["edit_requested"].append(sid)
                continue
        elif it["kind"] == "text":
            parsed = parse_free_text(it.get("text", ""))
            awaiting = _load()["awaiting_edit"].get(phone)
            if awaiting:
                sid = awaiting
                if parsed and parsed["action"] == "edit":
                    decision = make_decision(sid, "edit", parsed["edited"])
                elif parsed and parsed["action"] == "decline":
                    decision = make_decision(sid, "decline")
                else:
                    client.send_text(phone, M.unknown_reply_text()); out["replies"] += 1
                    continue
            elif parsed:
                decision = make_decision(sid, parsed["action"], parsed.get("edited"))
            else:
                client.send_text(phone, M.unknown_reply_text()); out["replies"] += 1
                continue
        if not decision:
            out["ignored"] += 1
            continue

        with _lock:
            d = _load()
            d["awaiting_edit"].pop(phone, None)
            if decision["suggestion_id"] in d["decided"]:
                out["ignored"] += 1
                continue
            d["decided"][decision["suggestion_id"]] = decision["action"]
            biz = d["business"].get(decision["suggestion_id"])
            _save(d)
        out["decisions"].append(decision)
        _emit(decision, biz)
        await _forward(decision)
        if decision["action"] == "decline":
            client.send_text(phone, M.decline_thanks_text()); out["replies"] += 1
    return out


def send_receipt(phone: str, apply_result: dict, client: W.WhatsAppClient | None = None) -> dict:
    """Called by the apply step: tell the customer where the hours now show."""
    return (client or W.get_client()).send_text(phone, M.receipt_text(apply_result))


# ------------------------------------------------------------------ HTTP

@router.get("/webhooks/whatsapp")
async def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == ensure_verify_token():
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "verify token mismatch")


def _signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header[7:])


@router.post("/webhooks/whatsapp")
async def inbound(request: Request):
    raw = await request.body()
    W.load_env()
    secret = os.environ.get("WA_APP_SECRET")
    if secret and not _signature_ok(secret, raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "bad json")
    res = await handle_payload(payload)
    return {"ok": True, "decisions": len(res["decisions"]), "statuses": len(res["statuses"])}  # Meta needs a fast 200


try:  # call lane: ElevenLabs post-call webhook
    from . import call_router
    router.include_router(call_router.router)
except Exception:
    pass
