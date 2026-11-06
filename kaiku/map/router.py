"""/map, /room, /join and the room API. Owned by the map builder."""
from __future__ import annotations

import io
import secrets

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from kaiku import events
from kaiku.schema import Event

from . import room

router = APIRouter()
COOKIE = "kaiku_room"


def _render(request: Request, name: str, **ctx):
    from kaiku.app import render
    return render(request, name, **ctx)


def _public(request: Request) -> str:
    from kaiku.config import settings
    return settings.PUBLIC_URL.rstrip("/")


def _question(biz: dict) -> dict:
    """The Kaiku question for jouluaatto from the suggest engine (cold start gives the ask)."""
    fallback = {"fi": "Oletteko auki jouluaattona 24.12.?", "en": "Are you open on Christmas Eve, 24 Dec?",
                "kind": "ask", "confidence": None}
    try:
        from kaiku.detect.engine import detect
        from kaiku.suggest.engine import suggest
        from kaiku.suggest.schema import Business
        b = Business(id=biz["id"], name=biz["name"], category=biz["category"], address=biz.get("address", ""),
                     city="Turku", lat=biz["lat"], lon=biz["lon"], website=biz.get("website"), source="osm")
        s = suggest(b, detect(b, room.HOLIDAY, use_network=False))
        out = dict(fallback, kind=s.kind, confidence=s.confidence)
        if s.kind == "ask":
            return out
        return out
    except Exception:  # noqa: BLE001
        return fallback


@router.get("/map", response_class=HTMLResponse)
def map_page(request: Request):
    return _render(request, "map.html", join_url=_public(request) + "/join", embed=False)


@router.get("/room", response_class=HTMLResponse)
def room_page(request: Request):
    return _render(request, "room.html", join_url=_public(request) + "/join", embed=True)


@router.get("/join", response_class=HTMLResponse)
def join_page(request: Request):
    token = request.cookies.get(COOKIE) or secrets.token_urlsafe(12)
    biz = room.assign(token)
    ctx = {"biz": biz, "q": _question(biz) if biz else None, "address": (biz or {}).get("address") or "Turun keskusta",
           "answered": bool(biz and biz["id"] in room.load_state()["answers"])}
    if ctx["answered"]:
        ctx["answer"] = room.load_state()["answers"][biz["id"]]["display"]
    resp = _render(request, "join.html", **ctx)
    resp.set_cookie(COOKIE, token, max_age=86400, httponly=True, samesite="lax")
    return resp


@router.post("/api/room/answer")
async def answer(request: Request, payload: dict = Body(...)):
    bid = str(payload.get("business_id") or "")
    biz = room.by_id(bid)
    if not biz:
        return JSONResponse({"ok": False, "error": "unknown business"}, status_code=404)
    a = room.record(bid, str(payload.get("answer") or ""), request.cookies.get(COOKIE, ""))
    disp = f"jouluaatto {a['display']}" if a["kind"] in ("hours",) else (
        "jouluaatto suljettu" if a["kind"] == "closed" else
        "jouluaatto normaalisti" if a["kind"] == "regular" else f"jouluaatto {a['display']}")
    base = {"map": True, "room": True, "lat": biz["lat"], "lon": biz["lon"], "name": biz["name"],
            "answer": a["display"], "display": disp, "holiday": room.HOLIDAY}
    events.emit(Event(step="decide", business_id=bid, title_fi=f"{biz['name']}: {disp}",
                      title_en=f"{biz['name']}: owner answered ({a['display']})", detail=dict(base, action="edit")))
    events.emit(Event(step="apply", business_id=bid, title_fi=f"{biz['name']}: piste vihreäksi",
                      title_en=f"{biz['name']}: dot turned green (demo)", detail=dict(base, note=room.NOTE)))
    return {"ok": True, "business_id": bid, "answer": a["display"]}


@router.get("/api/room/state")
def state():
    return room.snapshot()


@router.get("/api/room/reset")
def reset():
    room.reset()
    events.emit(Event(step="learn", title_fi="Huoneen vastaukset nollattu", title_en="Room answers cleared",
                      detail={"map": True, "reset": True}))
    return {"ok": True}


@router.get("/api/room/qr.svg")
def qr(request: Request):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(_public(request) + "/join", image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode().replace('<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n', "")
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})
