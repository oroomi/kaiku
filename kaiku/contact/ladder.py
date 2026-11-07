"""Contact ladder: step 1 email with the decision link (when the business has an owner_email), step 2 WhatsApp
(buttons) after EMAIL_ESCALATE_AFTER_S with no decision, step 3 a phone call by Kaiku after WA_ESCALATE_AFTER_S.
A decision from any channel cancels the pending steps. Language per owner (owner_language): English by default, "fi" for Finnish."""
from __future__ import annotations

import os
import re
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
    from kaiku import demo_contact as DC
    if DC.phone():  # the demo contact (set in the drawer) beats OWNER_WHATSAPP
        return W.normalize_phone(DC.phone())
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


REPLY_LINE = {"en": "Just reply yes, or tell me what the hours should be, and I'll take care of the rest.",
              "fi": "Vastaa kyllä tai kerro oikeat aukioloajat, niin hoidan loput."}


def buttons_enabled() -> bool:
    """Accept / Discard buttons under the warm opener by default (one tap to accept or discard, an edit is typed);
    WA_BUTTONS=0 sends the opener as one plain text instead."""
    W.load_env()
    return (os.environ.get("WA_BUTTONS") or "1").strip() != "0"


def _warm_opener(s: dict, name: str, en: str, d: str, prop: str, text: str, tail: str) -> str:
    """The first WhatsApp message, in the voice of a helpful assistant: who I am, why I write, what I noticed
    (every fact from the suggestion's own message), one ask. The owner reads this one line on a phone."""
    from kaiku.suggest import feed as F  # type: ignore
    msg = s.get("message_en") or ""
    m_ly = re.search(r"Last year you were (open [0-9:.\-]+|closed)", msg)
    m_reg = re.search(r"regular (\w+) hours \(([0-9:.\-]+)\)", msg)
    m_wd = re.search(r"is on (\w+day)", msg)
    ly = F._short_times(m_ly.group(1)) if m_ly else None
    reg = F._short_times(m_reg.group(2)) if m_reg else None
    wd = m_wd.group(1) if m_wd else (m_reg.group(1) if m_reg else "")
    month = (s.get("holiday_date") or "")[5:7]
    hol = en or "the holiday"
    lines = [f"Hi {name}! \U0001F44B It's Kaiku, your assistant at Fonecta Connect."]
    if month in ("12", "01"):
        lines.append("Christmas is around the corner, and I want to make sure none of your customers turn up at a closed door.")
    else:
        lines.append(f"{hol} is coming up, and I want to make sure none of your customers turn up at a closed door.")
    if ly and reg:
        when = f"{hol} ({wd} {d} this year)" if wd else f"{hol} ({d})"
        lines.append(f"Last year you were {ly} on {when}, but Connect still shows your regular hours, {reg}, for that day.")
    else:
        lines.append(text)
    if prop and prop != "closed":
        ask = f"Shall I set {prop} for {hol} on Google, Fonecta and everywhere else Connect publishes?"
    elif prop == "closed":
        ask = f"Shall I mark {hol} as closed everywhere Connect publishes?"
    else:
        ask = "Shall I update it everywhere Connect publishes?"
    lines.append(f"{ask} {tail}")
    return "\n\n".join(lines)


BUTTON_TAIL = {"en": "Tap Accept to save it or Discard to leave it. To change the hours, just reply with them.",
               "fi": "Paina Hyväksy tai Hylkää. Jos haluat muuttaa aukioloaikoja, vastaa niillä."}


def chat_text_for(s: dict, buttons: bool = False) -> str:
    """The WhatsApp opening as ONE plain text: the same intro and suggestion lines the website chat shows on load
    (kaiku.chat.router.opening), then "Reply in your own words." Finnish owners and businesses the chat does not know
    get the suggestion text instead."""
    lang = M.owner_lang(s)
    tail = (BUTTON_TAIL if buttons else REPLY_LINE)["fi" if lang == "fi" else "en"]
    if lang != "fi":
        try:
            from kaiku import store  # type: ignore
            from kaiku.chat import router as CR  # type: ignore
            bid = s.get("business_id")
            b = store.get_business(bid) if bid else None
            if b is not None:
                # ONE item per message, the same hand-over question the website chat asks after Accept
                from kaiku.suggest import feed as F  # type: ignore
                en = s.get("holiday_name_en") or ""
                d = F._dm(s["holiday_date"]) if s.get("holiday_date") else ""
                prop = F._hshort(s.get("proposed"))
                text = F._chat_text(s.get("message_en") or body_for(s), en, d, prop)
                text = re.sub(r"^Hi,?\s[^!\n]*!\s*", "", text)  # the WhatsApp body greets with "Hi, <name>!"
                text = re.sub(r"We suggest your hours are [^.]*\.", f"I suggest {prop}." if prop else "", text)
                text = re.sub(r"\s*Approve with one tap[^.]*\.(\s*The decision is always yours\.)?", " ", text).strip()
                if prop and "suggest" not in text.lower():
                    text += f" I suggest {prop}."
                name = s.get("business_name") or getattr(b, "name", None) or "there"
                try:  # the reply that follows continues on this suggestion
                    CR.session("wa:" + owner_phone(s))["focus"] = s.get("id")
                except Exception:
                    pass
                return _warm_opener(s, name, en, d, prop, text, tail)
        except Exception:
            pass
    return body_for(s) + "\n\n" + tail


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


def _log(s: dict, channel: str, detail: str, title_en: str | None = None, title_fi: str | None = None,
         message_en: str | None = None) -> None:
    """message_en = the text the owner actually received; the owner page thread shows it."""
    entry = {"channel": channel, "at": _now(), "detail": detail}
    s.setdefault("channel_log", []).append(entry)
    try:
        from kaiku import events  # type: ignore
        events.emit(events.Event(ts=entry["at"], step="contact", business_id=s.get("business_id"), suggestion_id=s.get("id"),
                                 title_fi=title_fi or f"Yhteydenotto: {channel}", title_en=title_en or f"Contact: {channel}",
                                 detail={"detail": detail, "channel": channel, **({"message_en": message_en} if message_en else {})}))
    except Exception:
        pass


def contact(suggestion: dict, client: W.WhatsAppClient | None = None, escalate_s: float | None = None,
            email_escalate_s: float | None = None) -> dict:
    """Start the ladder: email first when an owner address exists (and the suggestion needs a decision), else WhatsApp."""
    s = suggestion
    pref = preferred_channel(s)
    if pref in ("whatsapp", "call") and s.get("kind") != "no_change":
        return _preferred(s, pref, client, escalate_s, email_escalate_s)
    to = E.owner_email(s)
    if to and s.get("kind") != "no_change":
        r = E.send_decision_email(s, to)
        if r.get("ok") and not r.get("dry_run"):
            _log(s, "email", "sent to " + E.mask(to), "Email sent with the decision link", "Sähköposti lähetetty päätöslinkillä",
                 message_en=f"Email to {E.mask(to)}: \"{r.get('subject') or 'your holiday hours, one question'}\" with the decision link.")
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


def preferred_channel(s: dict) -> str | None:
    """The owner's own answer to "how do you want me to reach you next time?" (kaiku.learn.prefs), None = not asked yet."""
    try:
        from kaiku.learn import prefs  # type: ignore
        return prefs.get_contact_channel(s.get("business_id") or "")
    except Exception:
        return None


def _preferred(s: dict, pref: str, client, escalate_s, email_escalate_s) -> dict:
    """Start with the channel the owner asked for; the others stay as escalation in the usual order:
    whatsapp -> email -> call, call -> whatsapp -> email. The call rung still obeys KAIKU_NO_CALL and outbound_allowed
    (call.place_call), WhatsApp and email still go through the guarded clients: a preference never bypasses them."""
    name = "WhatsApp" if pref == "whatsapp" else "a call"
    _log(s, pref, f"preferred channel: {pref}", f"Reaching the owner by {name} first (their preference)" if pref == "whatsapp"
         else "Reaching the owner by call first (their preference)",
         "Otetaan yhteyttä ensin WhatsAppilla (omistajan toive)" if pref == "whatsapp" else "Otetaan yhteyttä ensin puhelulla (omistajan toive)")
    delay = escalate_s if escalate_s is not None else escalate_after_s()
    if pref == "whatsapp":
        _whatsapp(s, client, escalate_s, after="email", email_escalate_s=email_escalate_s)
    else:
        _call_step(s, first=True)
        if not is_decided(s["id"]):
            _schedule(s, delay, _wa_after_call, (s, client, escalate_s, email_escalate_s))
    return s


def _wa_after_call(s: dict, client=None, escalate_s: float | None = None, email_escalate_s: float | None = None) -> str:
    _timers.pop(s["id"], None)
    if is_decided(s["id"]):
        return "decided"
    _log(s, "whatsapp", "no decision after the call", "No answer to the call, WhatsApp next", "Ei vastausta puheluun, seuraavaksi WhatsApp")
    _whatsapp(s, client, escalate_s, after="email", email_escalate_s=email_escalate_s, final=True)
    return "sent"


def _email_step(s: dict, client=None, escalate_s: float | None = None, email_escalate_s: float | None = None,
                final: bool = False) -> str:
    """The email rung of a preferred-channel ladder: send the decision link, then (unless email was the last rung) the call."""
    _timers.pop(s["id"], None)
    if is_decided(s["id"]):
        return "decided"
    to = E.owner_email(s)
    if to:
        _log(s, "email", "no decision on the first channel", "No reply yet, email with the decision link next", "Ei vastausta, seuraavaksi sähköposti")
        r = E.send_decision_email(s, to)
        if r.get("ok") and not r.get("dry_run"):
            _log(s, "email", "sent to " + E.mask(to), "Email sent with the decision link", "Sähköposti lähetetty päätöslinkillä",
                 message_en=f"Email to {E.mask(to)}: \"{r.get('subject') or 'your holiday hours, one question'}\" with the decision link.")
        elif r.get("ok"):
            _log(s, "email", "dry run: " + str(r.get("path")), "Email drafted (dry run, no SMTP configured)",
                 "Sähköposti luonnosteltu (testitila, SMTP ei käytössä)")
        else:
            _log(s, "email", f"failed: {r.get('error')}", "Email failed", "Sähköposti epäonnistui")
    if not final:
        _schedule_call(s, escalate_s if escalate_s is not None else escalate_after_s())
    return "sent"


def _wa_step(s: dict, client=None, escalate_s: float | None = None) -> str:
    _timers.pop(s["id"], None)
    if is_decided(s["id"]):
        return "decided"
    if s.get("channel_log") and s["channel_log"][-1].get("channel") == "email":
        _log(s, "whatsapp", "no decision after the email", "No reply by email, WhatsApp next", "Ei vastausta sähköpostiin, seuraavaksi WhatsApp")
    _whatsapp(s, client, escalate_s)
    return "sent"


def _after_whatsapp(s: dict, delay: float, after: str, client, escalate_s, email_escalate_s, final: bool) -> None:
    """What follows a WhatsApp rung: the call (default ladder) or, in a preferred-channel ladder, the email first."""
    if after == "email":
        _schedule(s, delay, _email_step, (s, client, escalate_s, email_escalate_s, final))
    else:
        _schedule_call(s, delay)


def _whatsapp(s: dict, client: W.WhatsAppClient | None = None, escalate_s: float | None = None, after: str = "call",
              email_escalate_s: float | None = None, final: bool = False) -> dict:
    client = client or W.get_client()
    phone = owner_phone(s)
    if not phone:
        _log(s, "whatsapp", "blocked: no recipient (OWNER_WHATSAPP missing)")
        return s
    use_buttons = buttons_enabled()
    body = body_for(s)
    btns = buttons_for(s)
    chat_text = None
    if s.get("kind") not in ("no_change", "ask"):
        if use_buttons:
            body = chat_text_for(s, buttons=True)  # the warm opener as the interactive body, Accept / Discard under it
        else:
            chat_text = chat_text_for(s)  # one text message, the same conversation as the website chat
    R.register_sent(phone, s["id"], None, s.get("business_id"), M.owner_lang(s))

    if btns is None:
        r = client.send_text(phone, body)
    elif chat_text is not None and not (template_name(M.owner_lang(s)) and s.get("kind") not in ("ask", "no_change")):
        r = client.send_text(phone, chat_text)
        if r.get("needs_template"):
            _log(s, "whatsapp", "outside 24 h window: template first, the text follows after the owner replies")
            R.set_pending_buttons(phone, s["id"], chat_text, None)
            r = client.send_template(phone)
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
        _log(s, "whatsapp", f"sent {s.get('kind')} message {r.get('message_id')}", message_en=(chat_text or body))
        if btns is not None:
            _after_whatsapp(s, escalate_s if escalate_s is not None else escalate_after_s(), after, client, escalate_s, email_escalate_s, final)
    else:
        _log(s, "whatsapp", f"failed: {r.get('error')}")
        if client.configured and not r.get("blocked"):
            _after_whatsapp(s, 0, after, client, escalate_s, email_escalate_s, final)  # WhatsApp unreachable: go straight to step 2
        else:  # no WhatsApp on this instance: the next rung waits its normal turn and never fires at once
            _after_whatsapp(s, escalate_s if escalate_s is not None else escalate_after_s(), after, client, escalate_s, email_escalate_s, final)
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


def _call_step(s: dict, first: bool = False) -> str:
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
        r = call.place_call(s) or {}
        if not r.get("ok"):  # disabled instance, unconfigured lane or a SIP failure: never say "calling"
            why = r.get("reason") or r.get("error") or "unknown"
            _log(s, "call", f"call not placed: {why}", f"Call not placed ({why})", f"Puhelua ei soitettu ({why})")
            return "failed"
        if first:
            _log(s, "call", "call placed first (the owner's preference)", "Kaiku is calling (the owner's preference)", "Kaiku soittaa (omistajan toive)")
        else:
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
