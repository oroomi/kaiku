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


def subject_for(s: dict) -> str:
    name = M.business_name(s)
    if M.owner_lang(s) == "fi":
        hol = M.holiday_name_genitive(s) if M._has_name(s) else "Poikkeuspäivän"
        return f"{name}: {hol} aukioloajat, yksi kysymys"
    hol = s.get("holiday_name_en") or "Exception day"
    return f"{name}: {hol} hours, one question"


def _proposal_en(s: dict) -> str:
    hol = s.get("holiday_name_en") or "that day"
    if s.get("kind") == "ask":
        return f"I do not have your hours for {hol} ({M.fi_date(s['holiday_date'])}). Could you tell me what they are?"
    if s.get("kind") == "closed" or s.get("proposed") == "closed":
        return f"I suggest you are closed on {hol} ({M.fi_date(s['holiday_date'])})."
    return f"I suggest your hours on {hol} ({M.fi_date(s['holiday_date'])}) are {M.en_hours(s.get('proposed'))}."


def _proposal_fi(s: dict) -> str:
    when = M.fi_date(s["holiday_date"])
    if s.get("kind") == "ask":
        return f"Minulla ei ole tietoa aukioloajoistanne {when}. Kertoisitko ne?"
    if s.get("kind") == "closed" or s.get("proposed") == "closed":
        return f"Ehdotan, että olette suljettu {when}."
    return f"Ehdotan, että aukioloaikanne {when} on {M.fi_hours(s.get('proposed'))}."


def build_message(s: dict, to_email: str) -> tuple[EmailMessage, dict]:
    """Returns (message, parts) where parts has subject, text, html, link."""
    fi = M.owner_lang(s) == "fi"
    link = decision_link(s)
    subject = subject_for(s)
    name = M.business_name(s)
    lines = [f"Hei, {name}!" if fi else f"Hi, {name}!", ""]
    ly = M._hours_of(M._last_year(s))
    if ly is not None:
        lines.append(f"Viime vuonna aukioloaikanne sinä päivänä oli {M.fi_hours(ly)}." if fi
                     else f"Last year your hours that day were {M.en_hours(ly)}.")
    gn = M._hours_of(M._google_now(s))
    if gn is not None:
        lines.append(f"Google näyttää nyt {M.fi_hours(gn)}." if fi else f"Google currently shows {M.en_hours(gn)}.")
    lines.append(_proposal_fi(s) if fi else _proposal_en(s))
    lines += ["", ("Hyväksy, muokkaa tai kieltäydy yhdellä napautuksella, kirjautumista ei tarvita:" if fi
                   else "Approve, edit or decline with one tap, no login needed:"), link, "",
              "Kaiku, Fonecta Connect"]
    text = "\n".join(lines)
    paras = "".join(f"<p>{escape(l)}</p>" for l in lines[:-4] if l)
    cta = escape("Avaa päätös" if fi else "Open the decision")
    html = (f'<html><body style="font-family:system-ui,sans-serif;font-size:16px;color:#1c2b2d">{paras}'
            f'<p>{escape(lines[-4])}</p><p><a href="{escape(link)}" style="background:#0f766e;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;display:inline-block">{cta}</a></p>'
            f'<p style="color:#667">{escape(link)}</p><p>Kaiku, Fonecta Connect</p></body></html>')
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
