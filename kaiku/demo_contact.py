"""Demo contact override: at the Q&A a visitor may receive the email, the WhatsApp message and the call on their own device.

Stored in data/demo_contact.json (gitignored). When set it beats OWNER_EMAIL / OWNER_WHATSAPP / the business record for the
email step, the WhatsApp step, the call and the WhatsApp receipt, and the inbound WhatsApp handler treats that phone as the owner.
Keyed endpoints: POST/GET/DELETE /api/demo/contact (X-Kaiku-Key header or ?key=). Real values are never logged: events carry masks."""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger("kaiku.demo_contact")
router = APIRouter()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+\d{8,15}$")
CHANNELS = ("email", "whatsapp", "call")


def _file() -> Path:
    from kaiku.contact import whatsapp as W
    return W.data_dir() / "demo_contact.json"


def load() -> dict:
    try:
        d = json.loads(_file().read_text())
        ch = d.get("channels")
        ch = [c for c in CHANNELS if c in ch] if isinstance(ch, list) else list(CHANNELS)
        return {"email": str(d.get("email") or "").strip(), "phone": str(d.get("phone") or "").strip(), "channels": ch}
    except FileNotFoundError:
        return {"email": "", "phone": "", "channels": list(CHANNELS)}
    except Exception:  # a contact file that exists but cannot be read: fail closed, email only, never the owner's phone
        return {"email": "", "phone": "", "channels": ["email"]}


def _mode_file() -> Path:
    return _file().with_name("try_mode.json")


def set_mode(channels, seconds: int) -> None:
    """Fail-closed marker written by the public try page: while it lasts, only these rungs may fire, whatever the contact
    file says later (cleared, overwritten or corrupt). The ladder reads it at fire time."""
    chs = [c for c in CHANNELS if c in (channels or [])]
    f = _mode_file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"channels": chs, "until": time.time() + float(seconds)}))
    os.replace(tmp, f)


def clear_mode() -> None:
    try:
        _mode_file().unlink()
    except FileNotFoundError:
        pass


def _mode() -> list | None:
    """The unexpired try-mode channels, None when there is no live marker; an unreadable marker means email only."""
    try:
        d = json.loads(_mode_file().read_text())
    except FileNotFoundError:
        return None
    except Exception:
        return ["email"]
    try:
        if float(d.get("until", 0)) > time.time():
            return [c for c in CHANNELS if c in (d.get("channels") or [])]
    except Exception:
        return ["email"]
    return None


def allows(ch: str) -> bool:
    """May this rung (email / whatsapp / call) fire? A live try-mode marker decides first; else the demo contact's channels;
    with no contact at all everything is allowed (the owner's own demo)."""
    m = _mode()
    if m is not None:
        return ch in m
    d = load()
    if not (d["email"] or d["phone"]):
        return ch in d["channels"]
    return ch in d["channels"]


def email() -> str:
    return load()["email"]


def phone() -> str:
    return load()["phone"]


def mask_email(a: str) -> str:
    if "@" not in a:
        return ""
    local, dom = a.split("@", 1)
    return (local[:1] + "***@" + dom)


def mask_phone(p: str) -> str:
    return (p[:4] + "***" + p[-3:]) if len(p) >= 8 else ""


def masked() -> dict:
    d = load()
    return {"email": mask_email(d["email"]), "phone": mask_phone(d["phone"]), "channels": d["channels"], "set": bool(d["email"] or d["phone"])}


def _check_key(request: Request) -> None:
    want = os.environ.get("KAIKU_ROOM_KEY", "")
    got = request.query_params.get("key", "") or request.headers.get("x-kaiku-key", "")
    if not want or not hmac.compare_digest(got.encode(), want.encode()):
        raise HTTPException(403, "The demo contact needs the key. / Avain puuttuu.")


def _emit(en: str) -> None:
    try:
        from kaiku import events
        from kaiku.schema import Event
        events.emit(Event(step="contact", business_id="furry-paw", title_fi=en, title_en=en, detail={}))
    except Exception:
        pass


def save(email_: str = "", phone_: str = "", channels=None) -> dict:
    """Validate and store; both empty clears. Raises ValueError with a plain message."""
    e, p = (email_ or "").strip(), re.sub(r"[ \-()]", "", (phone_ or "").strip())
    if e and not _EMAIL.match(e):
        raise ValueError("The email needs an @ and a dot after it, like name@company.fi.")
    if p and not _PHONE.match(p):
        raise ValueError("The phone must start with + and have 8 to 15 digits, like +358401234567.")
    if not e and not p:
        clear()
        return masked()
    chs = [c for c in CHANNELS if c in channels] if isinstance(channels, (list, tuple)) else list(CHANNELS)
    f = _file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"email": e, "phone": p, "channels": chs}))
    os.replace(tmp, f)
    m = masked()
    _emit("Demo contact set: " + ", ".join(x for x in (m["email"], m["phone"]) if x))
    return m


def clear() -> None:
    had = bool(load()["email"] or load()["phone"])
    try:
        _file().unlink()
    except FileNotFoundError:
        pass
    try:  # a cleared contact must not leave a pending WhatsApp or call that would then fall back to the owner's own phone
        from kaiku.contact import ladder as _ladder
        _ladder.cancel_pending()
    except Exception:
        pass
    if had:
        _emit("Demo contact cleared: back to the owner's own")


@router.get("/api/demo/contact")
def api_get(request: Request):
    _check_key(request)
    return masked()


@router.post("/api/demo/contact")
async def api_set(request: Request):
    _check_key(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        return save(str(body.get("email") or ""), str(body.get("phone") or ""), body.get("channels"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/demo/contact")
def api_clear(request: Request):
    _check_key(request)
    clear()
    return masked()
