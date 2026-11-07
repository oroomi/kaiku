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
    for k in ("messages", "latest", "awaiting_edit", "pending_buttons", "last_inbound", "decided", "business", "lang"):
        d.setdefault(k, {})
    d.setdefault("seen", [])
    return d


def _save(d: dict) -> None:
    d["seen"] = d["seen"][-300:]
    tmp = _ctx_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_ctx_path())


def register_sent(phone: str, suggestion_id: str, wa_message_id: str | None = None, business_id: str | None = None,
                  lang: str | None = None) -> None:
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
        if lang:
            d["lang"][suggestion_id] = lang
        _save(d)


def set_pending_buttons(phone: str, suggestion_id: str, body: str, buttons=None) -> None:
    with _lock:
        d = _load()
        d["pending_buttons"][W.normalize_phone(phone)] = {"suggestion_id": suggestion_id, "body": body,
                                                          "buttons": buttons or W.DEFAULT_BUTTONS,
                                                          "text_only": buttons is None}
        _save(d)


def has_window(phone: str) -> bool:
    """True when the phone wrote to us in the last 24 h (free-form messages allowed)."""
    t = _load()["last_inbound"].get(W.normalize_phone(phone))
    return bool(t) and time.time() - t < 24 * 3600


def is_decided(suggestion_id: str) -> bool:
    return suggestion_id in _load()["decided"]


# ------------------------------------------------------------------ free text

_APPROVE = {"ok", "okei", "kyllä", "kylla", "jees", "joo", "juu", "hyväksyn", "hyvä", "k", "yes", "kyl", "selvä", "sopii",
            "approve", "approved", "okay", "sure", "yeah", "yep", "yup", "y", "go ahead", "sounds good", "looks good",
            "please do", "do it", "that works", "fine", "all good"}
_DECLINE = {"ei", "ei kiitos", "en", "ei muutosta", "no", "ei halua", "älä muuta", "ala muuta",
            "no thanks", "no thank you", "nope", "decline", "n", "not now", "skip", "dont", "don't", "do not change",
            "no change", "leave it", "leave it as is", "keep it", "no thanks."}
_CLOSED = {"suljettu", "kiinni", "kiinni koko päivän", "ei auki", "olemme kiinni", "closed", "we are closed", "we're closed",
           "close", "closed all day", "closed the whole day", "not open"}
_HOURS = re.compile(r"^(?:klo\.?\s*|from\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\s*(?:-|\u2013|\u2014|to|until|till|asti)\s*(?:klo\.?\s*)?"
                    r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?$")
_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12}


def _hhmm(h: str, m: str | None) -> str | None:
    h_i, m_i = int(h), int(m or 0)
    if not (0 <= h_i <= 24 and 0 <= m_i < 60):
        return None
    return f"{h_i:02d}:{m_i:02d}"


def _h24(h: str, ap: str | None) -> str:
    n = int(h)
    if ap == "am":
        n = 0 if n == 12 else n
    elif ap == "pm":
        n = n if n == 12 else n + 12
    return str(n)


def parse_free_text(text: str) -> dict | None:
    """-> {'action':'approve'} | {'action':'decline'} | {'action':'edit','edited':'closed'|[{start,end}]} | None.
    Understands English and Finnish: yes/approve/ok/sure, no/no thanks, '9-13', '9am-1pm', 'nine to one', 'closed'."""
    t = re.sub(r"[!.?,]+$", "", (text or "").strip().lower())
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^(?:the hours? (?:are|is)|open|we(?:'re| are) open|hours?:?) ", "", t)
    if not t:
        return None
    t = re.sub(r"\b(" + "|".join(_NUMWORD) + r")\b", lambda m: str(_NUMWORD[m[1]]), t) if " to " in t else t
    if t in _CLOSED:
        return {"action": "edit", "edited": "closed"}
    if t in _APPROVE:
        return {"action": "approve"}
    if t in _DECLINE:
        return {"action": "decline"}
    m = _HOURS.match(t)
    if m:
        a = _hhmm(_h24(m[1], m[3]), m[2])
        b_h = _h24(m[4], m[6])
        if not m[6] and not m[3] and int(m[4]) < int(m[1]) <= 12:  # "9 to 1" -> 9-13
            b_h = str(int(m[4]) + 12)
        b = _hhmm(b_h, m[5])
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


def _lang(sid: str | None) -> str | None:
    """Owner language remembered when the suggestion was sent; None = default (English)."""
    return _load()["lang"].get(sid or "")


def make_decision(sid: str, action: str, edited=None, via: str = "whatsapp") -> dict:
    return {"suggestion_id": sid, "action": action, "edited": edited, "reason_chip": None,
            "standing_permission": False, "via": via, "at": _now()}


# ------------------------------------------------------------------ the website chat brain on WhatsApp

DEFAULT_BUSINESS = "furry-paw"
MAX_MSG = 400


def session_id(phone: str) -> str:
    return "wa:" + W.normalize_phone(phone)


def feed_id_for(bid: str, sid: str | None) -> str | None:
    """The chat feed card behind a suggestion id: sid itself when the feed lists it, else the holiday card with the
    same business and holiday date (a chain run stores its suggestion under its own id, the feed under feed-<biz>-...)."""
    if not sid:
        return None
    try:
        from kaiku import store  # type: ignore
        from kaiku.chat import feed as F  # type: ignore
        if F.find(bid, sid) is not None:
            return sid
        sg = store.get_suggestion(sid)
        day = getattr(sg, "holiday_date", None) if sg else None
        if not day or getattr(sg, "business_id", bid) != bid:
            return None
        for i in F.get_feed(bid).get("suggestions", []):
            if i.get("kind") == "holiday_hours" and i.get("holiday_date") == day:
                return i["id"]
    except Exception:
        return None
    return None


def _business_for(sid: str | None) -> str | None:
    """The chat business behind a suggestion (or the demo business): None when the chat does not know it."""
    try:
        from kaiku import store  # type: ignore
    except ImportError:
        return None
    cands = [_load()["business"].get(sid or "")]
    try:
        sg = store.get_suggestion(sid) if sid else None
        cands.append(getattr(sg, "business_id", None))
    except Exception:
        pass
    cands.append(DEFAULT_BUSINESS)
    for c in cands:
        if not c or store.get_business(c) is None:
            continue
        if sid:  # an id the chat feed does not list (not even by holiday date) belongs to somebody else
            try:
                if feed_id_for(c, sid) is None:
                    continue
            except Exception:
                continue
        return c
    return None


def _is_owner_phone(phone: str) -> bool:
    W.load_env()
    own = W.normalize_phone(os.environ.get("OWNER_WHATSAPP"))
    return bool(own) and own == W.normalize_phone(phone)


def chat_session(phone: str) -> dict:
    """The same session store the website chat uses; one session per phone, so a second message continues it."""
    from kaiku.chat import router as CR  # type: ignore
    s = CR.session(session_id(phone))
    s["via"] = "whatsapp"
    return s


async def chat_turn(phone: str, text: str, bid: str, focus: str | None = None) -> tuple[str, list]:
    """One inbound text through the chat brain. Raises when the brain is unusable (caller falls back to the keyword parser)."""
    from kaiku.chat import brain, feed as F, router as CR  # type: ignore
    s = chat_session(phone)
    s["t"] = time.time()
    if focus:
        s["focus"] = focus
    ids = {i["id"] for i in F.get_feed(bid).get("suggestions", [])}
    if s.get("focus") not in ids:  # a chain-run id, or nothing after a restart: focus the feed card for the last sent suggestion
        fid = feed_id_for(bid, s.get("focus") or _load()["latest"].get(phone))
        if fid:
            s["focus"] = fid
    msg = (text or "").strip()[:MAX_MSG]
    reply, acts = await brain.respond(bid, s, msg)
    s["hist"] += [("user", msg), ("assistant", reply)]
    s["log"] += [{"role": "user", "kind": "chat", "text": msg}, {"role": "kaiku", "kind": "chat", "text": reply}]
    f = brain.focus_of(F.get_feed(bid).get("suggestions", []), s)
    s["focus"] = f["id"] if f else None
    return reply, acts


async def _run_decision(decision: dict) -> bool:
    """A WhatsApp decision runs through the web chat's own path: chain.on_decision when a chain run is waiting, else
    chain.post_decision (kaiku.chat.actions.decide). True when the chat path handled it."""
    sid = decision["suggestion_id"]
    bid = _business_for(sid)
    if not bid:
        return False
    try:
        from kaiku.chat import actions as A, feed as F  # type: ignore
        if F.find(bid, sid) is None:
            return False
        edited = decision.get("edited")
        r = await A.decide(bid, sid, decision["action"], edited, via="whatsapp")
        return bool(r.get("ok"))
    except Exception as e:
        log.warning("chat decide failed (%s), using chain.on_decision", type(e).__name__)
        return False


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
            st = {k: it.get(k) for k in ("message_id", "status", "to", "errors")}
            out["statuses"].append(st)
            try:  # delivery proof for the demo: data/wa_status.jsonl (sent / delivered / read / failed + Meta error codes)
                with open(W.data_dir() / "wa_status.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"at": _now(), **st}, ensure_ascii=False) + "\n")
                if st.get("status") == "failed" or st.get("errors"):
                    log.warning("whatsapp status failed: %s", json.dumps(st.get("errors"), ensure_ascii=False)[:300])
            except Exception as e:  # never break the 200 to Meta
                log.warning("wa_status log failed: %s", e)
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
            if pend.get("text_only"):
                r = client.send_text(phone, pend["body"])
            else:
                r = client.send_buttons(phone, pend["body"], [tuple(b) for b in pend["buttons"]])
            if r.get("ok"):
                register_sent(phone, pend["suggestion_id"], r.get("message_id"))
            out["replies"] += 1
            continue
        if it["kind"] == "text" and (sid or _is_owner_phone(phone)):
            handled = await _chat_text(phone, it.get("text", ""), sid, client, out)
            if handled:
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
                client.send_text(phone, M.unknown_suggestion_text(_lang(sid))); out["replies"] += 1
                out["unknown"].append(sid)
                continue
            if act == "approve":
                decision = make_decision(sid, "approve")
            elif act == "decline":
                decision = make_decision(sid, "decline")
            elif act == "edit":
                with _lock:
                    d = _load(); d["awaiting_edit"][phone] = sid; _save(d)
                try:
                    chat_session(phone)["focus"] = sid
                except Exception:
                    pass
                client.send_text(phone, M.edit_prompt_text(_lang(sid))); out["replies"] += 1
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
                    client.send_text(phone, M.unknown_reply_text(_lang(sid))); out["replies"] += 1
                    continue
            elif parsed:
                decision = make_decision(sid, parsed["action"], parsed.get("edited"))
            else:
                client.send_text(phone, M.unknown_reply_text(_lang(sid))); out["replies"] += 1
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
        if not await _run_decision(decision):
            _emit(decision, biz)
            await _forward(decision)
        if decision["action"] == "decline":
            client.send_text(phone, M.decline_thanks_text(_lang(sid))); out["replies"] += 1
    return out


async def _chat_text(phone: str, text: str, sid: str | None, client: W.WhatsAppClient, out: dict) -> bool:
    """Any inbound text goes to the chat brain; its reply goes back as a WhatsApp text. False = brain unavailable, the
    keyword parser takes over (yes / no / new times), so the lane never goes silent."""
    bid = _business_for(sid)
    if not bid or not (text or "").strip():
        return False
    try:
        with _lock:
            d = _load()
            awaiting = d["awaiting_edit"].pop(phone, None)
            _save(d)
        reply, acts = await chat_turn(phone, text, bid, awaiting)
    except Exception as e:
        log.warning("chat brain failed on WhatsApp (%s), keyword parser", type(e).__name__)
        return False
    for a in acts:
        if a.get("type") == "decided":
            dec = make_decision(a["suggestion_id"], a["action"])
            with _lock:
                d = _load(); d["decided"][dec["suggestion_id"]] = dec["action"]; _save(d)
            out["decisions"].append(dec)
    if reply:
        client.send_text(phone, reply)
        out["replies"] += 1
    return True


def send_receipt(phone: str, apply_result: dict, client: W.WhatsAppClient | None = None) -> dict:
    """Called by the apply step: tell the customer where the hours now show."""
    r = dict(apply_result)
    if not r.get("owner_language"):
        r["owner_language"] = _lang(r.get("suggestion_id")) or None
    if not r.get("holiday_date") and r.get("suggestion_id"):
        try:  # the receipt names the date ("Christmas Eve 24.12.")
            from kaiku import store  # type: ignore
            r["holiday_date"] = store.get_suggestion(r["suggestion_id"]).holiday_date
        except Exception:
            pass
    return (client or W.get_client()).send_text(phone, M.receipt_text(r))


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
