"""/admin?key=...: one keyed hub for the team, Fonecta and the judges. Same key rule as /console and /judge (403 without it).
No new backend logic: the page reuses the console's endpoints and links to the live FIWARE pages."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    from kaiku import app as A
    k = A._keyed(request)
    # The key reaches the template only for the keyed links (judge, console). A header or cookie key is not echoed.
    qk = request.query_params.get("key", "") if k else ""
    resp = A._page(request, "admin.html", keyed=k, key=qk)
    if not k:
        resp.status_code = 403
    return resp
