"""/console?key=...: one phone-width page for the person at the Q&A table. Who Kaiku reaches, the customer we were given, run it.
Same key rule as /judge. No new backend logic: the page reuses /api/demo/contact, /api/listing, /api/score, /api/run and /api/reset."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def last_call() -> str:
    """One line from data/call_log.jsonl: time and ok or the reason. No ids, no numbers."""
    try:
        from kaiku.contact import call as C
        lines = [x for x in C.log_path().read_text(encoding="utf-8").splitlines() if x.strip()]
        rec = json.loads(lines[-1])
    except Exception:
        return "Last call: none yet."
    try:
        at = datetime.fromisoformat(str(rec.get("at", "")).replace("Z", "+00:00")).strftime("%d.%m. %H:%M UTC")
    except ValueError:
        at = str(rec.get("at", ""))[:16]
    what = "ok" if rec.get("ok") else "failed: " + str(rec.get("reason") or "no reason logged")[:80]
    return f"Last call: {at}, {what}."


@router.get("/console", response_class=HTMLResponse)
def console(request: Request):
    from kaiku import app as A
    k = A._keyed(request)
    resp = A._page(request, "console.html", keyed=k, last_call=last_call() if k else "")
    if not k:
        resp.status_code = 403
    return resp
