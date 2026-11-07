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
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger("kaiku.demo_contact")
router = APIRouter()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+\d{8,15}$")


def _file() -> Path:
    from kaiku.contact import whatsapp as W
    return W.data_dir() / "demo_contact.json"


def load() -> dict:
    try:
        d = json.loads(_file().read_text())
        return {"email": str(d.get("email") or "").strip(), "phone": str(d.get("phone") or "").strip()}
    except Exception:
        return {"email": "", "phone": ""}


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
    return {"email": mask_email(d["email"]), "phone": mask_phone(d["phone"]), "set": bool(d["email"] or d["phone"])}


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


def save(email_: str = "", phone_: str = "") -> dict:
    """Validate and store; both empty clears. Raises ValueError with a plain message."""
    e, p = (email_ or "").strip(), re.sub(r"[ \-()]", "", (phone_ or "").strip())
    if e and not _EMAIL.match(e):
        raise ValueError("The email needs an @ and a dot after it, like name@company.fi.")
    if p and not _PHONE.match(p):
        raise ValueError("The phone must start with + and have 8 to 15 digits, like +358401234567.")
    if not e and not p:
        clear()
        return masked()
    f = _file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"email": e, "phone": p}))
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
        return save(str(body.get("email") or ""), str(body.get("phone") or ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/demo/contact")
def api_clear(request: Request):
    _check_key(request)
    clear()
    return masked()
