"""Contact ladder: step 1 email with the decision link (when the business has an owner_email), step 2 WhatsApp
(buttons) after EMAIL_ESCALATE_AFTER_S with no decision, step 3 a phone call by Kaiku after WA_ESCALATE_AFTER_S.
A decision from any channel cancels the pending steps. Language per owner (owner_language): English by default, "fi" for Finnish."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from . import email as E
from . import messages as M
from . import router as R
from . import whatsapp as W

# Demo: 120 s. Production: 24 h (86400), i.e. the length of the WhatsApp service window.
DEFAULT_ESCALATE_S = 120
DEFAULT_EMAIL_ESCALATE_S = 120

_timers: dict[str, threading.Timer] = {}
_timer_factory = threading.Timer  # tests swap in a fake that records (delay, fn, args)


def email_escalate_after_s() -> float:
    W.load_env()
    try:
        return float(os.environ.get("EMAIL_ESCALATE_AFTER_S", DEFAULT_EMAIL_ESCALATE_S))
    except ValueError:
        return DEFAULT_EMAIL_ESCALATE_S


def is_decided(sid: str) -> bool:
    """A decision from ANY channel (WhatsApp reply, web link, call, voice) ends the ladder."""
    if R.is_decided(sid):
        return True
    try:
        from kaiku import store  # type: ignore
        if store.get_decisions(sid):
            return True
        sg = store.get_suggestion(sid)
        return bool(sg and sg.status in ("approved", "edited", "declined", "applied"))
    except Exception:
        return False


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
    fi = M.owner_lang(s) == "fi"
    if s.get("kind") == "ask":
        return [("edit", "Kerron aikani"), ("decline", "Ei kiitos")] if fi else [("edit", "Tell my hours"), ("decline", "No thanks")]
    if s.get("kind") == "no_change":
        return None  # informational only
    return [(f"{a}:{s['id']}", t) for a, t in W.buttons_for_lang(M.owner_lang(s))]


def body_for(s: dict) -> str:
    return M.suggestion_text(s)


def template_name(lang: str = "fi") -> str:
    """WA_TEMPLATE_NAME (e.g. kaiku_hours_fi) switches step 1 to the approved template. Unset = interactive buttons.
    Finnish owners use WA_TEMPLATE_NAME; English owners only use a template when WA_TEMPLATE_NAME_EN (an approved
    English template with the same parameters) is set, otherwise the English interactive buttons go out."""
    W.load_env()
    if lang == "en":
        return (os.environ.get("WA_TEMPLATE_NAME_EN") or "").strip()
    return (os.environ.get("WA_TEMPLATE_NAME") or "").strip()



def _template_reason(s: dict) -> str:
    """Template param {{4}} (Peruste): the first reason in the owner's language, else the holiday name."""
    en = M.owner_lang(s) == "en"
    for r in s.get("reasons") or []:
        t = (r or {}).get("text_en" if en else "text_fi") or ""
        if t.strip():
            return t.strip().rstrip(".")[:200]
    return (s.get("holiday_name_en") or "that day") if en else M.holiday_name(s).lower()

def _send_hours_template(client: W.WhatsAppClient, phone: str, s: dict, name: str) -> dict:
    lang = M.owner_lang(s)
    hrs = M.en_hours(s.get("proposed")).replace(" to ", "-") if lang == "en" else M.fi_hours(s.get("proposed"))
    return client.send_template_hours(phone, M.business_name(s), M.fi_date(s["holiday_date"]), hrs,
                                      _template_reason(s), s["id"], name, lang)


def _log(s: dict, channel: str, detail: str, title_en: str | None = None, title_fi: str | None = None) -> None:
    entry = {"channel": channel, "at": _now(), "detail": detail}
    s.setdefault("channel_log", []).append(entry)
    try:
        from kaiku import events  # type: ignore
        events.emit(events.Event(ts=entry["at"], step="contact", business_id=s.get("business_id"), suggestion_id=s.get("id"),
                                 title_fi=title_fi or f"Yhteydenotto: {channel}", title_en=title_en or f"Contact: {channel}",
                                 detail={"detail": detail, "channel": channel}))
    except Exception:
        pass


def contact(suggestion: dict, client: W.WhatsAppClient | None = None, escalate_s: float | None = None,
            email_escalate_s: float | None = None) -> dict:
    """Start the ladder: email first when an owner address exists (and the suggestion needs a decision), else WhatsApp."""
    s = suggestion
    to = E.owner_email(s)
    if to and s.get("kind") != "no_change":
        r = E.send_decision_email(s, to)
        if r.get("ok") and not r.get("dry_run"):
            _log(s, "email", "sent to " + E.mask(to), "Email sent with the decision link", "Sähköposti lähetetty päätöslinkillä")
        elif r.get("ok"):
            _log(s, "email", "dry run: " + str(r.get("path")), "Email drafted (dry run, no SMTP configured)",
                 "Sähköposti luonnosteltu (testitila, SMTP ei käytössä)")
        else:
            _log(s, "email", f"failed: {r.get('error')}", "Email failed, WhatsApp next", "Sähköposti epäonnistui, seuraavaksi WhatsApp")
        s["status"] = "sent"
        delay = email_escalate_s if email_escalate_s is not None else email_escalate_after_s()
        _schedule(s, 0 if not r.get("ok") else delay, _wa_step, (s, client, escalate_s))
        return s
    return _whatsapp(s, client, escalate_s)


def _wa_step(s: dict, client=None, escalate_s: float | None = None) -> str:
    _timers.pop(s["id"], None)
    if is_decided(s["id"]):
        return "decided"
    if s.get("channel_log") and s["channel_log"][-1].get("channel") == "email":
        _log(s, "whatsapp", "no decision after the email", "No reply by email, WhatsApp sent", "Ei vastausta sähköpostiin, WhatsApp lähetetty")
    _whatsapp(s, client, escalate_s)
    return "sent"


def _whatsapp(s: dict, client: W.WhatsAppClient | None = None, escalate_s: float | None = None) -> dict:
    client = client or W.get_client()
    phone = owner_phone(s)
    if not phone:
        _log(s, "whatsapp", "blocked: no recipient (OWNER_WHATSAPP missing)")
        return s
    body = body_for(s)
    btns = buttons_for(s)
    R.register_sent(phone, s["id"], None, s.get("business_id"), M.owner_lang(s))

    if btns is None:
        r = client.send_text(phone, body)
    elif template_name(M.owner_lang(s)) and s.get("kind") not in ("ask", "no_change"):
        r = _send_hours_template(client, phone, s, template_name(M.owner_lang(s)))  # works outside the 24 h window too
    else:
        r = client.send_buttons(phone, body, btns)
        if r.get("needs_template"):
            _log(s, "whatsapp", "outside 24 h window: template first, buttons follow after the owner replies")
            R.set_pending_buttons(phone, s["id"], body, btns)
            r = client.send_template(phone)
    if r.get("ok"):
        R.register_sent(phone, s["id"], r.get("message_id"), s.get("business_id"), M.owner_lang(s))
        s["status"] = "sent"
        _log(s, "whatsapp", f"sent {s.get('kind')} message {r.get('message_id')}")
        if btns is not None:
            _schedule_call(s, escalate_s if escalate_s is not None else escalate_after_s())
    else:
        _log(s, "whatsapp", f"failed: {r.get('error')}")
        _schedule_call(s, 0)  # WhatsApp unreachable: go straight to step 2
    return s


def _schedule(s: dict, delay: float, fn, args: tuple) -> None:
    sid = s["id"]
    old = _timers.pop(sid, None)
    if old:
        old.cancel()
    t = _timer_factory(delay, fn, args=args)
    t.daemon = True
    _timers[sid] = t
    t.start()


def _schedule_call(s: dict, delay: float) -> None:
    _schedule(s, delay, _call_step, (s,))


def _call_step(s: dict) -> str:
    _timers.pop(s["id"], None)
    if is_decided(s["id"]):
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
        _log(s, "call", "call placed after no WhatsApp decision", "No reply on WhatsApp, Kaiku is calling", "Ei vastausta WhatsAppiin, Kaiku soittaa")
        return "placed"
    except Exception as e:
        _log(s, "call", f"call failed: {type(e).__name__}")
        return "failed"


def cancel(sid: str) -> None:
    """Cancel the pending ladder step of one suggestion (call this when a decision arrives)."""
    t = _timers.pop(sid, None)
    if t:
        t.cancel()


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
