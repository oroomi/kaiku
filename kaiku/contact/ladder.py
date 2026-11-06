"""Contact ladder: step 1 WhatsApp (buttons), step 2 a phone call by Kaiku if no decision. No email, ever."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from . import messages as M
from . import router as R
from . import whatsapp as W

# Demo: 120 s. Production: 24 h (86400), i.e. the length of the WhatsApp service window.
DEFAULT_ESCALATE_S = 120

_timers: dict[str, threading.Timer] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def escalate_after_s() -> float:
    W.load_env()
    try:
        return float(os.environ.get("WA_ESCALATE_AFTER_S", DEFAULT_ESCALATE_S))
    except ValueError:
        return DEFAULT_ESCALATE_S


def owner_phone(s: dict) -> str:
    """Demo rule: every recipient is the owner's own phone from .env (OWNER_WHATSAPP). Real owners never get contacted."""
    W.load_env()
    return W.normalize_phone(os.environ.get("OWNER_WHATSAPP") or s.get("owner_whatsapp"))


def buttons_for(s: dict):
    if s.get("kind") == "ask":
        return [("edit", "Kerron aikani"), ("decline", "Ei kiitos")]
    if s.get("kind") == "no_change":
        return None  # informational only
    return [(f"{a}:{s['id']}", t) for a, t in W.DEFAULT_BUTTONS]


def body_for(s: dict) -> str:
    return M.suggestion_text(s)


def _log(s: dict, channel: str, detail: str) -> None:
    entry = {"channel": channel, "at": _now(), "detail": detail}
    s.setdefault("channel_log", []).append(entry)
    try:
        from kaiku import events  # type: ignore
        events.emit(events.Event(ts=entry["at"], step="contact", business_id=s.get("business_id"), suggestion_id=s.get("id"),
                                 title_fi=f"Yhteydenotto: {channel}", title_en=f"Contact: {channel}", detail={"detail": detail}))
    except Exception:
        pass


def contact(suggestion: dict, client: W.WhatsAppClient | None = None, escalate_s: float | None = None) -> dict:
    """Step 1 of the ladder. Returns the suggestion with channel_log (and status 'sent' when a message went out)."""
    s = suggestion
    client = client or W.get_client()
    phone = owner_phone(s)
    if not phone:
        _log(s, "whatsapp", "blocked: no recipient (OWNER_WHATSAPP missing)")
        return s
    body = body_for(s)
    btns = buttons_for(s)
    R.register_sent(phone, s["id"], None, s.get("business_id"))

    if btns is None:
        r = client.send_text(phone, body)
    else:
        r = client.send_buttons(phone, body, btns)
        if r.get("needs_template"):
            _log(s, "whatsapp", "outside 24 h window: template first, buttons follow after the owner replies")
            R.set_pending_buttons(phone, s["id"], body, btns)
            r = client.send_template(phone)
    if r.get("ok"):
        R.register_sent(phone, s["id"], r.get("message_id"), s.get("business_id"))
        s["status"] = "sent"
        _log(s, "whatsapp", f"sent {s.get('kind')} message {r.get('message_id')}")
        if btns is not None:
            _schedule_call(s, escalate_s if escalate_s is not None else escalate_after_s())
    else:
        _log(s, "whatsapp", f"failed: {r.get('error')}")
        _schedule_call(s, 0)  # WhatsApp unreachable: go straight to step 2
    return s


def _schedule_call(s: dict, delay: float) -> None:
    sid = s["id"]
    old = _timers.pop(sid, None)
    if old:
        old.cancel()
    t = threading.Timer(delay, _call_step, args=(s,))
    t.daemon = True
    _timers[sid] = t
    t.start()


def _call_step(s: dict) -> str:
    _timers.pop(s["id"], None)
    if R.is_decided(s["id"]):
        return "decided"
    try:
        from kaiku.contact import call  # type: ignore
    except ImportError:
        call = None
    if call is None or not hasattr(call, "place_call"):
        _log(s, "call", "call lane not configured")
        return "not_configured"
    try:
        call.place_call(s)
        _log(s, "call", "call placed after no WhatsApp decision")
        return "placed"
    except Exception as e:
        _log(s, "call", f"call failed: {type(e).__name__}")
        return "failed"


def cancel_pending() -> None:
    for t in list(_timers.values()):
        t.cancel()
    _timers.clear()


try:  # core lands in parallel
    from kaiku import chain  # type: ignore
    if hasattr(chain, "register"):
        chain.register("contact", contact)
except ImportError:
    pass
