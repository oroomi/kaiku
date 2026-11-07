"""Contact ladder step 1: a short email with the one-tap decision link (no login).

English by default, Finnish per owner_language. Transport: SMTP over STARTTLS from env
SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_FROM_NAME ("Kaiku, Fonecta Connect").
Without SMTP_HOST/SMTP_FROM nothing leaves: the full message is written to data/email_outbox/<ts>_<sid>.eml
and the result is {"ok": True, "dry_run": True}. Every attempt is logged to data/email_log.jsonl
(no secrets, the recipient is masked to its domain)."""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

from . import messages as M
from . import whatsapp as W

DEFAULT_FROM_NAME = "Kaiku, Fonecta Connect"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def smtp_config() -> dict | None:
    """SMTP settings from env, or None when not configured (dry run). KAIKU_NO_SMTP=1 forces the dry run (the test suite)."""
    if os.environ.get("KAIKU_NO_SMTP") == "1" or not W.outbound_allowed():
        return None
    W.load_env()
    host = (os.environ.get("SMTP_HOST") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip()
    if not host or not sender:
        return None
    try:
        port = int(os.environ.get("SMTP_PORT") or 587)
    except ValueError:
        port = 587
    return {"host": host, "port": port, "user": (os.environ.get("SMTP_USER") or "").strip(),
            "password": os.environ.get("SMTP_PASS") or "", "from": sender,
            "from_name": (os.environ.get("SMTP_FROM_NAME") or DEFAULT_FROM_NAME).strip()}


def owner_email(s: dict) -> str:
    """OWNER_EMAIL (a real address for the demo) wins; else the suggestion's or business's owner_email."""
    W.load_env()
    from kaiku import demo_contact as DC
    if DC.email():  # the demo contact (set in the drawer) beats everything
        return DC.email()
    v = (os.environ.get("OWNER_EMAIL") or "").strip() or (s.get("owner_email") or "").strip()
    if not v:
        try:
            from kaiku import store  # type: ignore
            b = store.get_business(s.get("business_id") or "")
            v = (getattr(b, "owner_email", None) or "").strip() if b else ""
        except Exception:
            v = ""
    return v if "@" in v else ""


def mask(addr: str) -> str:
    return "***@" + addr.split("@", 1)[1] if "@" in addr else "***"


def decision_link(s: dict) -> str:
    link = s.get("decide_url")
    if link:
        return link
    try:
        from kaiku.decide import tokens  # type: ignore
        return tokens.link_for(s["id"], s.get("business_id") or "")
    except Exception:
        base = os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210"
        return base.rstrip("/") + "/d/" + s["id"]


_ALLATIVE = {"jouluaatto": "jouluaatolle", "joulupäivä": "joulupäivälle", "tapaninpäivä": "tapaninpäivälle",
             "uudenvuodenaatto": "uudenvuodenaatolle", "uudenvuodenpäivä": "uudenvuodenpäivälle",
             "loppiainen": "loppiaiselle", "vappu": "vapulle", "juhannusaatto": "juhannusaatolle"}


def _for_fi(s: dict) -> str:
    """'jouluaatolle' for a known holiday, else 'päivälle 24.12.'."""
    if not M._has_name(s):
        return f"päivälle {M.fi_date(s['holiday_date'])}"
    n = M.holiday_name(s).lower()
    if n in _ALLATIVE:
        return _ALLATIVE[n]
    if n.endswith("päivä"):
        return n + "lle"
    if n.endswith("nen"):
        return n[:-3] + "selle"
    return f"päivälle {M.fi_date(s['holiday_date'])}"


def subject_for(s: dict) -> str:
    name = M.business_name(s)
    if M.owner_lang(s) == "fi":
        hol = M.holiday_name_genitive(s).lower() if M._has_name(s) else "poikkeuspäivän"
        return f"{name}: {hol} aukioloajat, yksi pikainen kysymys"
    hol = s.get("holiday_name_en")
    return f"{name}: your {hol} hours, one quick question" if hol else f"{name}: your hours for a special day, one quick question"


def _is_closed(s: dict) -> bool:
    return s.get("kind") == "closed" or s.get("proposed") == "closed"


def _intro_and_ask(s: dict, fi: bool) -> tuple[str, str]:
    """(paragraph 1, paragraph 2) in plain words; every fact kept: holiday, date, last year's hours, proposal."""
    date = M.fi_date(s["holiday_date"])
    named = M._has_name(s) if fi else bool(s.get("holiday_name_en"))
    ly = M._hours_of(M._last_year(s))
    web = M._hours_of(M._signal(s, "website"))
    gn = M._hours_of(M._google_now(s))
    prop = None if _is_closed(s) else s.get("proposed")
    ph = M.fi_hours(prop) if prop and prop != "closed" else None
    stale = gn is None or gn != prop
    if fi:
        hol = M.holiday_name(s)
        p1 = [f"{hol} ({date}) lähestyy." if named else f"Päivä {date} lähestyy."]
        if s.get("kind") == "ask":
            p1.append("Minulla ei ole tietoa aukioloajoistanne sinä päivänä.")
        elif ly is not None:
            p1.append("Viime vuonna olitte sinä päivänä suljettuina" if ly == "closed" else f"Viime vuonna olitte auki {M.fi_hours(ly)}")
            p1[-1] += ", ja tällä hetkellä tietosi näyttävät vielä normaalit aukioloajat." if stale else "."
        elif web is not None:
            p1.append(f"Verkkosivunne mukaan olette auki {M.fi_hours(web)}.")
        else:
            p1.append("Viime vuoden aukioloaikoja minulla ei tästä päivästä ole.")
        tail = "Napauta alta ja sano kyllä, muuta ajat tai jätä ennalleen. Ei kirjautumista, vie muutaman sekunnin."
        if s.get("kind") == "ask":
            p2 = "Kertoisitko, mitkä ajat sinä päivänä on? Napauta alta ja kirjoita ne. Ei kirjautumista, vie muutaman sekunnin."
        elif _is_closed(s):
            p2 = (f"Merkitsenkö teidät suljetuiksi {M.essive(M.holiday_name(s))}? " if named else "Merkitsenkö teidät sinä päivänä suljetuiksi? ") + tail
        else:
            p2 = (f"Laitanko {_for_fi(s)} {ph}? " if named else f"Laitanko {date} ajaksi {ph}? ") + tail
        return " ".join(p1), p2
    hol = s.get("holiday_name_en") or "That day"
    p1 = [f"{hol} ({date}) is coming up." if named else f"{date} is coming up."]
    if s.get("kind") == "ask":
        p1.append("I don't have your hours for that day.")
    elif ly is not None:
        p1.append("Last year you were closed that day" if ly == "closed" else f"Last year you were open {M.en_hours(ly)} that day")
        p1[-1] += ", and right now your listing still shows your normal hours." if stale else "."
    elif web is not None:
        p1.append(f"Your website says {M.en_hours(web)}.")
    else:
        p1.append("I don't have last year's hours for that day.")
    on = hol if named else "that day"
    tail = "Tap below and say yes, change the hours, or leave it as it is. No login needed, it takes a few seconds."
    if s.get("kind") == "ask":
        p2 = "Could you tell me what they are? Tap below and type them in. No login needed, it takes a few seconds."
    elif _is_closed(s):
        p2 = f"Shall I mark you closed on {on}? " + tail
    else:
        p2 = f"Shall I set {M.en_hours(prop)} for {on}? " + tail
    return " ".join(p1), p2


def build_message(s: dict, to_email: str) -> tuple[EmailMessage, dict]:
    """Returns (message, parts) where parts has subject, text, html, link."""
    fi = M.owner_lang(s) == "fi"
    link = decision_link(s)
    subject = subject_for(s)
    name = M.business_name(s)
    p1, p2 = _intro_and_ask(s, fi)
    hi = f"Hei {name}!" if fi else f"Hi {name}!"
    after = "Kun päätät, päivitämme tietosi kaikkialle." if fi else "Once you decide, we'll update your information everywhere."
    sign = "Kaiku, avustajasi Fonecta Connectissa" if fi else "Kaiku, your assistant at Fonecta Connect"
    cta_txt = "Avaa päätös" if fi else "Open the decision"
    text = "\n".join([hi, "", p1, "", p2, "", f"{cta_txt}: {link}", "", after, "", sign])
    cta = escape(cta_txt)
    html = (f'<html><body style="font-family:system-ui,sans-serif;font-size:16px;color:#1c2b2d"><p>{escape(hi)}</p>'
            f'<p>{escape(p1)}</p><p>{escape(p2)}</p>'
            f'<p><a href="{escape(link)}" style="background:#0f766e;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;display:inline-block">{cta}</a></p>'
            f'<p style="color:#667">{escape(link)}</p><p>{escape(after)}</p><p>{escape(sign)}</p></body></html>')
    cfg = smtp_config()
    sender = (cfg or {}).get("from") or "kaiku@example.invalid"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(((cfg or {}).get("from_name") or DEFAULT_FROM_NAME, sender))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg, {"subject": subject, "text": text, "html": html, "link": link}


def _log(entry: dict) -> None:
    try:
        with open(W.data_dir() / "email_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def send_decision_email(suggestion: dict, to_email: str) -> dict:
    """Send (or dry-run) the decision email. Never raises. Returns {"ok", "dry_run"?, "path"?, "error"?, "subject"}."""
    s = suggestion
    sid = s.get("id") or "unknown"
    entry = {"at": _now(), "suggestion_id": sid, "to": mask(to_email or ""), "channel": "email"}
    if not to_email or "@" not in to_email:
        entry.update(ok=False, error="no recipient")
        _log(entry)
        return {"ok": False, "error": "no recipient"}
    try:
        msg, parts = build_message(s, to_email)
    except Exception as e:  # malformed suggestion
        entry.update(ok=False, error=f"build failed: {type(e).__name__}")
        _log(entry)
        return {"ok": False, "error": entry["error"]}
    cfg = smtp_config()
    if cfg is None:
        out = W.data_dir() / "email_outbox"
        out.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)
        path = out / f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}_{safe}.eml"
        path.write_bytes(bytes(msg))
        entry.update(ok=True, dry_run=True, subject=parts["subject"], file=path.name)
        _log(entry)
        return {"ok": True, "dry_run": True, "path": str(path), "subject": parts["subject"]}
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg, from_addr=cfg["from"], to_addrs=[to_email])
        entry.update(ok=True, dry_run=False, subject=parts["subject"])
        _log(entry)
        return {"ok": True, "dry_run": False, "subject": parts["subject"]}
    except Exception as e:
        entry.update(ok=False, error=type(e).__name__)  # class name only, never the server text
        _log(entry)
        return {"ok": False, "error": type(e).__name__}
