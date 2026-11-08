"""/try and /api/try. Door email: the ladder stops after the email. Door phone: the visitor's own number, full ladder.
Guard rails: a pause switch, Helsinki call hours, daily caps, one tester at a time. Only masks are ever logged or returned."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from kaiku import demo_contact as DC

router = APIRouter()
HEL = ZoneInfo("Europe/Helsinki")
LOCK_S = 150
OPEN_FROM, OPEN_TO = 8, 22
CAP_PHONE_PER_DAY, CAP_EMAIL_PER_DAY, CAP_PHONE_DOOR_TOTAL = 1, 3, 10
MODE_S = 20 * 60  # the try-mode marker outlives the longest ladder (email 60 s, WhatsApp 600 s, then the call)
PAUSED_MSG = "Try-it is paused during the live final. Come to the stand instead."


def _dir() -> Path:
    from kaiku.contact import whatsapp as W
    return W.data_dir()


def _now() -> datetime:
    return datetime.now(HEL)


def _paused() -> bool:
    return os.environ.get("KAIKU_TRY_OFF") == "1" or (_dir() / "try_off").exists()


def _h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


def _log_rows() -> list[dict]:
    rows = []
    try:
        for line in (_dir() / "try_log.jsonl").read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return rows


def _today_rows(now: datetime) -> list[dict]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return [r for r in _log_rows() if float(r.get("ts", 0)) >= start]


def _lock_left() -> int:
    try:
        until = float(json.loads((_dir() / "try_lock.json").read_text()).get("until", 0))
    except Exception:
        return 0
    return max(0, int(until - time.time() + 0.999))


def _open_hours_now(now: datetime) -> bool:
    return OPEN_FROM <= now.hour < OPEN_TO


def _next_day_text(now: datetime) -> str:
    return (now + timedelta(days=1)).strftime("%d.%m.") + " at midnight Finnish time"


@router.get("/try", response_class=HTMLResponse)
def try_page(request: Request):
    from kaiku.app import render
    return render(request, "try.html")


@router.get("/api/try/status")
def status():
    now = _now()
    rows = _today_rows(now)
    return {"paused": _paused(), "busy": _lock_left() > 0, "seconds_left": _lock_left(),
            "calls_left_today": max(0, CAP_PHONE_DOOR_TOTAL - sum(1 for r in rows if r.get("door") == "phone")),
            "open_hours": "08-22 Helsinki"}


@router.post("/api/try")
async def try_it(request: Request):
    if _paused():
        raise HTTPException(503, PAUSED_MSG)
    raw = await request.body()
    if len(raw) > 2048:
        raise HTTPException(413, "That is more than a form needs.")
    try:
        body = json.loads(raw)
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    door = body.get("door")
    if door not in ("email", "phone"):
        raise HTTPException(400, "Pick a door: email or phone.")
    email_in = str(body.get("email") or "").strip()
    phone_in = re.sub(r"[ \-()]", "", str(body.get("phone") or "").strip()) if door == "phone" else ""
    if not email_in:
        raise HTTPException(400, "Type your email address first.")
    if door == "phone":
        if not phone_in:
            raise HTTPException(400, "Type your phone number, starting with +, like +358401234567.")
        if body.get("own_number") is not True:
            raise HTTPException(400, "Tick the box: this must be your own number.")
    if len(email_in) > 254 or len(phone_in) > 20:
        raise HTTPException(400, "That is too long for an email address or a phone number.")
    if not DC._EMAIL.match(email_in):
        raise HTTPException(400, "The email needs an @ and a dot after it, like name@company.fi.")
    if phone_in and not DC._PHONE.match(phone_in):
        raise HTTPException(400, "The phone must start with + and have 8 to 15 digits, like +358401234567.")
    now = _now()
    if door == "phone" and not _open_hours_now(now):
        raise HTTPException(400, "Kaiku calls between 8 and 22 Finnish time; the email door works around the clock.")
    rows = _today_rows(now)
    eh, ph = _h(email_in.lower()), (_h(phone_in) if phone_in else "")
    if ph and any(r.get("phone_sha256") == ph for r in rows):
        raise HTTPException(429, f"This number has already been tried today. It opens again {_next_day_text(now)}.")
    if sum(1 for r in rows if r.get("email_sha256") == eh) >= CAP_EMAIL_PER_DAY:
        raise HTTPException(429, f"This email has had its 3 tries today. It opens again {_next_day_text(now)}.")
    if door == "phone" and sum(1 for r in rows if r.get("door") == "phone") >= CAP_PHONE_DOOR_TOTAL:
        raise HTTPException(429, f"The phone door is full for today. It opens again {_next_day_text(now)}; the email door is open.")
    left = _lock_left()
    if left > 0:
        return JSONResponse({"detail": f"Kaiku is with someone else right now, try again in about {left} seconds", "seconds_left": left}, status_code=409)
    lock = _dir() / "try_lock.json"
    lock.write_text(json.dumps({"until": time.time() + LOCK_S}))

    from kaiku import chain
    try:
        await chain.reset_demo(contact=0)
        chans = ["email"] if door == "email" else ["email", "whatsapp", "call"]
        DC.save(email_in, phone_in, channels=chans)
        DC.set_mode(chans, MODE_S)  # fail closed for the whole ladder window, even if the contact is cleared or overwritten
        run = await chain.api_run(business="furry-paw", date="2026-12-24")
    except Exception:
        try:
            lock.unlink()
        except OSError:
            pass
        raise
    m = DC.masked()
    with (_dir() / "try_log.jsonl").open("a") as f:
        f.write(json.dumps({"ts": time.time(), "door": door, "email_mask": m["email"], "phone_mask": m["phone"],
                            "email_sha256": eh, "phone_sha256": ph}) + "\n")
    return {"ok": True, "suggestion_id": (run or {}).get("suggestion_id"), "door": door,
            "contact": {"email": m["email"], "phone": m["phone"], "channels": m["channels"]}, "seconds_locked": LOCK_S}
