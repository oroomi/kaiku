"""Aura routes: page, entities (from the broker), SSE stream, notify webhook, agent ask, subscriptions, status."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from . import agent, models, subs

log = logging.getLogger("aura.router")
router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "aura_cache" / "latest.json"
BUSINESSES = ROOT / "data" / "turku_businesses.json"
NG = subs.NG
FRESH = {"bus": 120, "ship": 300}

templates = Jinja2Templates(directory=str(ROOT / "kaiku" / "web" / "templates"))
STATIC = ROOT / "kaiku" / "web" / "static"


def _asset_v() -> str:
    try:
        return str(int(max(p.stat().st_mtime for p in STATIC.iterdir() if p.is_file())))
    except ValueError:
        return "0"


templates.env.globals.setdefault("asset_v", _asset_v)

_recent: list[dict] = []        # last notifications, newest last
_queues: set[asyncio.Queue] = set()
_state = {"source": "unknown", "polled": None}


# ------------------------------------------------------------------ reading the broker
async def read_broker() -> dict:
    """Records from the BROKER (not the feeds). Falls back to the feeder's cache file."""
    h = {"Accept": "application/json", "Link": models.link(models.SDM_TRANSPORT)}
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            rv, rw = await asyncio.gather(
                c.get(f"{NG}/entities", params={"type": "Vehicle", "limit": 1000}, headers=h),
                c.get(f"{NG}/entities", params={"type": "WeatherObserved", "limit": 5},
                      headers={**h, "Link": models.link(models.SDM_WEATHER)}))
        rv.raise_for_status()
        buses, ships, weather = [], [], None
        for e in rv.json():
            c = models.compact(e)
            if not c:
                continue
            if models.age_s(c.get("obs")) > FRESH.get(c["kind"], 300):
                continue
            (ships if c["kind"] == "ship" else buses).append(c)
        if rw.status_code == 200 and rw.json():
            weather = models.compact(rw.json()[0])
        _state["source"] = "broker"
        return {"buses": buses, "ships": ships, "weather": weather, "source": "broker"}
    except (httpx.HTTPError, ValueError) as e:
        log.warning("broker read failed: %s", e)
    try:
        d = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        d = {}
    _state["source"] = "fallback cache"
    return {"buses": d.get("buses", []), "ships": d.get("ships", []), "weather": d.get("weather"), "source": "fallback cache"}


def _counts(d: dict) -> dict:
    w = d.get("weather") or {}
    return {"buses": len(d["buses"]), "ships": len(d["ships"]), "weather": 1 if w else 0,
            "entities": len(d["buses"]) + len(d["ships"]) + (1 if w else 0)}


def _brief(d: dict) -> dict:
    """Compact delta: arrays [id, lon, lat, heading, label]."""
    return {"buses": [[b["id"], b["lon"], b["lat"], b.get("heading"), b.get("line") or "", b.get("dest") or "", b.get("delay")] for b in d["buses"]],
            "ships": [[s["id"], s["lon"], s["lat"], s.get("heading"), s.get("name") or ""] for s in d["ships"]],
            "weather": d.get("weather"), "counts": _counts(d), "source": d["source"]}


# ------------------------------------------------------------------ pages and data
@router.get("/aura", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(request, "aura.html", {})


@router.get("/api/aura/entities")
async def entities(type: str = "Vehicle"):
    d = await read_broker()
    if type == "WeatherObserved":
        return {"source": d["source"], "entities": [d["weather"]] if d["weather"] else []}
    return {"source": d["source"], "entities": d["buses"] + d["ships"]}


@router.get("/api/aura/businesses")
def businesses():
    try:
        raw = json.loads(BUSINESSES.read_text())
        items = raw if isinstance(raw, list) else raw.get("businesses", [])
        return {"source": "data/turku_businesses.json", "items": [[b.get("lon"), b.get("lat"), b.get("name", "")] for b in items
                                                                   if b.get("lon") is not None and b.get("lat") is not None]}
    except (OSError, ValueError):
        return {"source": None, "items": []}


@router.get("/api/aura/status")
async def status():
    d = await read_broker()
    version = None
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            version = (await c.get(subs.BROKER + "/version")).json().get("orionld version")
    except (httpx.HTTPError, ValueError):
        pass
    try:
        polled = json.loads(CACHE.read_text()).get("polled")
    except (OSError, ValueError):
        polled = None
    return {"counts": _counts(d), "source": d["source"], "broker": version or "down", "last_polled": polled,
            "feeds": FEEDS, "subscriptions": len(subs.list_active())}


FEEDS = [
    {"id": "foli", "name": "Föli", "url": "data.foli.fi/siri/vm", "licence": "CC BY 4.0", "poll_s": 10},
    {"id": "ais", "name": "Fintraffic Digitraffic", "url": "meri.digitraffic.fi AIS", "licence": "CC BY 4.0", "poll_s": 20},
    {"id": "wx", "name": "Open-Meteo", "url": "api.open-meteo.com", "licence": "CC BY 4.0", "poll_s": 300},
]


# ------------------------------------------------------------------ SSE
def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/api/aura/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues.add(q)

    async def gen():
        try:
            yield _sse("hello", {"recent": _recent[-10:]})
            last = 0.0
            while True:
                if await request.is_disconnected():
                    break
                if time.time() - last >= 5:
                    last = time.time()
                    yield _sse("positions", _brief(await read_broker()))
                try:
                    yield _sse("notification", await asyncio.wait_for(q.get(), timeout=1))
                except asyncio.TimeoutError:
                    pass
        finally:
            _queues.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ notifications
def _fmt_dist(m: float) -> str:
    return f"{round(m)} m" if m < 1000 else f"{m / 1000:.1f} km".replace(".", ",")


def _fmt_dist_en(m: float) -> str:
    return f"{round(m)} m" if m < 1000 else f"{m / 1000:.1f} km"


def build_notices(payload: dict) -> list[dict]:
    p = subs.by_subscription(payload.get("subscriptionId", "")) or {}
    out = []
    for e in payload.get("data", []):
        c = models.compact(e) or {}
        d = None
        if p.get("geo_center") and "lon" in c:
            d = models.haversine_m(c["lon"], c["lat"], p["geo_center"][0], p["geo_center"][1])
        what_fi = f"linja {c['line']}" if c.get("kind") == "bus" and c.get("line") else ("alus " + str(c.get("name") or "")) if c.get("kind") == "ship" else str(c.get("name") or e.get("id"))
        what_en = f"line {c['line']}" if c.get("kind") == "bus" and c.get("line") else ("ship " + str(c.get("name") or "")) if c.get("kind") == "ship" else str(c.get("name") or e.get("id"))
        place_fi = p.get("place_label_fi") or "kohteesta"
        place_en = (p.get("description_en") or "").strip() and "the watched place" or "the watched place"
        dist_fi = f" {_fmt_dist(d)}" if d is not None else ""
        dist_en = f"{_fmt_dist_en(d)} " if d is not None else ""
        out.append({"ts": models.iso(), "entity": e.get("id"), "subscription": payload.get("subscriptionId"), "distance_m": round(d) if d is not None else None,
                    "title_fi": f"Tilaus laukesi: {what_fi} on{dist_fi} {place_fi}",
                    "title_en": f"Subscription fired: {what_en} is {dist_en}from {p.get('place_label_en') or place_en}",
                    "notification_id": payload.get("id")})
    return out


@router.post("/aura/notify")
async def notify(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=204)
    notices = sorted(build_notices(payload), key=lambda n: n["distance_m"] if n["distance_m"] is not None else 1e9)
    for n in notices[:1]:  # one line per delivery: the nearest entity; the rest are counted
        n["others"] = len(notices) - 1
        _recent.append(n)
        del _recent[:-50]
        for q in list(_queues):
            try:
                q.put_nowait(n)
            except asyncio.QueueFull:
                pass
        try:
            from kaiku import events
            from kaiku.schema import Event
            events.emit(Event(step="broker", title_fi=n["title_fi"], title_en=n["title_en"],
                              detail={"entity": n["entity"], "distance_m": n["distance_m"], "subscription": n["subscription"], "source": "aura"}))
        except Exception as e:  # noqa: BLE001  events are a nice-to-have here
            log.info("event emit skipped: %s", e)
    return Response(status_code=204)


# ------------------------------------------------------------------ agent and subscriptions
@router.post("/api/aura/ask")
async def ask(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    try:
        return await asyncio.to_thread(agent.ask, text)
    except Exception as e:  # noqa: BLE001
        log.warning("agent failed: %s", e)
        return JSONResponse({"proposal": None, "explanation_fi": "Avustaja ei vastannut, yritä uudelleen.",
                             "explanation_en": "The assistant did not answer, try again."}, status_code=502)


@router.post("/api/aura/subscriptions/{pid}/approve")
async def approve(pid: str):
    try:
        res = await asyncio.to_thread(subs.approve, pid)
    except KeyError:
        raise HTTPException(404, "no such proposal")
    except ValueError as e:
        raise HTTPException(409, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "subscription_id": res["subscription"]["id"], "subscription": res["subscription"], "proposal": res["proposal"]}


@router.post("/api/aura/subscriptions/{pid}/reject")
async def reject(pid: str):
    if not subs.reject(pid):
        raise HTTPException(409, "not pending")
    return {"ok": True}


@router.get("/api/aura/subscriptions")
async def list_subs():
    return {"items": await asyncio.to_thread(subs.list_active)}


@router.delete("/api/aura/subscriptions/{sid:path}")
async def delete_sub(sid: str):
    await asyncio.to_thread(subs.delete, sid)
    return {"ok": True}
