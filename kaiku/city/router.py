"""/city: Turku, one broker. 813 OSM businesses as NGSI-LD Store entities, Föli buses and AIS ships, all read from
Orion-LD; a room answer is written to the broker and the broker's notification (not a poll) turns the dot green."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from kaiku.broker.client import LINK, broker_url
from kaiku.broker.fallback import as_list

from . import seed as seed_mod

log = logging.getLogger("kaiku.city")
router = APIRouter()
SUB_NAME = "kaiku-city-store-status"
HOLIDAY = seed_mod.HOLIDAY
TZ = ZoneInfo("Europe/Helsinki")
NOTIFY_ATTRS = ["holidayHoursStatus", "name", "location"]

_queues: set[asyncio.Queue] = set()
_recent: list[dict] = []           # last approvals pushed from notifications, newest last
_seen: dict[tuple, float] = {}     # (id, observedAt) -> monotonic time, 5 s dedupe
_seen_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
DEDUPE_S = 5.0


def _async_client(**kw) -> httpx.AsyncClient:  # tests swap this for a MockTransport client
    return httpx.AsyncClient(**kw)


def ng() -> str:
    return broker_url() + "/ngsi-ld/v1"


def notify_url() -> str:
    base = os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210"
    return base.rstrip("/") + "/city/notify"


def _val(e: dict, k: str):
    v = e.get(k)
    if isinstance(v, list):
        v = next((i for i in v if isinstance(i, dict) and not i.get("datasetId")), v[0] if v else None)
    return v.get("value") if isinstance(v, dict) else v


def hours_display(h) -> str | None:
    if h is None:
        return None
    if h in ("closed", "regular"):
        return h
    if isinstance(h, list):
        return ", ".join(f"{_short(s.get('start'))}-{_short(s.get('end'))}" for s in h if isinstance(s, dict)) or None
    if isinstance(h, dict):
        return h.get("text")
    return str(h)


def _short(t: str | None) -> str:
    """'09:00' -> '9', '09:30' -> '9:30'."""
    try:
        h, m = str(t).split(":")[:2]
        return str(int(h)) + ("" if m == "00" else f":{m}")
    except ValueError:
        return str(t or "?")


def parse_hours(answer: dict):
    """room.parse_answer() result -> holidayHours value: [{start,end}] | "closed" | "regular" | {"text": ...}."""
    kind = answer.get("kind")
    if kind in ("closed", "regular"):
        return kind
    m = re.match(r"^(\d{1,2})(?::(\d\d))?-(\d{1,2})(?::(\d\d))?$", str(answer.get("hours") or ""))
    if kind == "hours" and m:
        return [{"start": f"{int(m[1]):02d}:{m[2] or '00'}", "end": f"{int(m[3]):02d}:{m[4] or '00'}"}]
    return {"text": answer.get("display") or ""}


def row_of(e: dict) -> dict | None:
    loc = _val(e, "location") or {}
    co = loc.get("coordinates") if isinstance(loc, dict) else None
    if not co:
        return None
    st = _val(e, "holidayHoursStatus") or {}
    s = st.get("status") if isinstance(st, dict) else None
    cat = _val(e, "category")
    row = {"id": e["id"].rsplit(":", 1)[-1], "n": _val(e, "name") or "", "c": (cat[0] if isinstance(cat, list) and cat else cat) or "",
           "lon": co[0], "lat": co[1], "s": "approved" if s == "approved" else "known" if s == "known" else "missing"}
    if row["s"] == "approved":
        hh = _val(e, "holidayHours")
        a = hours_display(hh.get("hours") if isinstance(hh, dict) else None)
        if a:
            row["a"] = a
    return row


def _counts(rows: list[dict]) -> dict:
    c = {"total": len(rows), "missing": 0, "known": 0, "approved": 0}
    for r in rows:
        c[r["s"]] += 1
    return c


def christmas() -> dict:
    now = datetime.now(TZ)
    d = (date(now.year, 12, 24) - now.date()).days
    return {"date": HOLIDAY, "days": d, "local_time": now.strftime("%H:%M"), "now": now.isoformat()}


async def read_stores() -> dict:
    """Rows from Orion-LD. On failure, rows from the room snapshot with source=fallback (the page says FALLBACK)."""
    params = {"type": "Store", "idPattern": seed_mod.ID_PATTERN, "limit": 1000,
              "attrs": "name,location,category,holidayHoursStatus,holidayHours"}
    try:
        async with _async_client(timeout=5) as c:
            r = await c.get(f"{ng()}/entities", params=params, headers={"Accept": "application/json", "Link": LINK})
        r.raise_for_status()
        rows = [x for x in (row_of(e) for e in r.json()) if x]
        if rows:
            return {"source": "orion-ld", "rows": rows, "counts": _counts(rows)}
        log.warning("city: broker returned no Store entities, using fallback")
    except (httpx.HTTPError, ValueError) as e:
        log.warning("city: broker read failed: %s", e)
    try:
        from kaiku.map import room
        snap = room.snapshot()
        rows = [{"id": b["id"], "n": b["n"], "c": b["c"], "lon": b["lon"], "lat": b["lat"],
                 "s": {"answered": "approved", "known": "known"}.get(b["s"], "missing"), **({"a": b["a"]} if b.get("a") else {})}
                for b in snap["businesses"]]
    except Exception as e:  # noqa: BLE001
        log.warning("city: fallback snapshot failed: %s", e)
        rows = []
    return {"source": "fallback", "rows": rows, "counts": _counts(rows)}


# ------------------------------------------------------------------ pages and data
@router.get("/city", response_class=HTMLResponse)
def city_page(request: Request):
    from kaiku.app import render
    q = request.query_params
    return render(request, "city.html", is_embed=q.get("embed") == "1", room=q.get("room") == "1",
                  join_url=(os.environ.get("PUBLIC_URL") or "").rstrip("/") + "/join")


@router.get("/api/city/stores")
async def stores(only: str = ""):
    d = await read_stores()
    rows = d["rows"] if only != "approved" else [r for r in d["rows"] if r["s"] == "approved"]
    return {"source": d["source"], "counts": d["counts"], "rows": rows, "holiday": christmas(),
            "attribution": "OpenStreetMap contributors, ODbL"}


async def _vehicles() -> dict:
    try:
        from kaiku.aura.router import read_broker
        return await read_broker()
    except ImportError:
        return {"buses": [], "ships": [], "weather": None, "source": "no data"}


def _brief(d: dict) -> dict:
    try:
        from kaiku.aura.router import _brief as aura_brief
        return aura_brief(d)
    except ImportError:
        return {"buses": [], "ships": [], "weather": None, "counts": {"buses": 0, "ships": 0}, "source": d.get("source")}


@router.get("/api/city/vehicles")
async def vehicles():
    return _brief(await _vehicles())


def judge_curl() -> str:
    return (f"curl -s -H 'Accept: application/ld+json' -H '" + "Link: " + LINK + "' "
            f"'{ng()}/entities?type=Store&limit=2'")


@router.get("/api/city/judge")
async def judge():
    ent = None
    try:
        async with _async_client(timeout=4) as c:
            r = await c.get(f"{ng()}/entities", params={"type": "Store", "idPattern": seed_mod.ID_PATTERN, "limit": 2},
                            headers={"Accept": "application/ld+json", "Link": LINK})
            r.raise_for_status()
            lst = r.json()
            ent = lst[0] if lst else None
    except (httpx.HTTPError, ValueError):
        pass
    return {"curl": judge_curl(), "entity": ent, "broker_up": ent is not None,
            "note": "Without the Link header Orion-LD cannot expand type=Store and returns an empty list."}


# ------------------------------------------------------------------ SSE
def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _push(item: dict) -> None:
    for q in list(_queues):
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass


@router.get("/api/city/stream")
async def stream(request: Request):
    global _loop
    _loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _queues.add(q)

    async def gen():
        try:
            yield _sse("hello", {"recent": _recent[-6:]})
            last = 0.0
            while True:
                if await request.is_disconnected():
                    break
                if time.time() - last >= 5:
                    last = time.time()
                    yield _sse("positions", _brief(await _vehicles()))
                try:
                    yield _sse("store", await asyncio.wait_for(q.get(), timeout=1))
                except asyncio.TimeoutError:
                    pass
        finally:
            _queues.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ the notification
def handle_notification(note: dict) -> list[dict]:
    """Approved Stores only (q on an object key is not evaluated by this Orion build). Deduped per (id, observedAt)."""
    out = []
    now = time.monotonic()
    for e in note.get("data", []) or []:
        eid = e.get("id", "")
        if not eid.startswith("urn:ngsi-ld:Store:osm-"):
            continue
        st = None
        for inst in as_list(e.get("holidayHoursStatus") or []):
            if isinstance(inst, dict) and isinstance(inst.get("value"), dict):
                st = inst
        if not st or st["value"].get("status") != "approved":
            continue
        key = (eid, st.get("observedAt") or "")
        with _seen_lock:
            for k in [k for k, t in _seen.items() if now - t > DEDUPE_S]:
                _seen.pop(k, None)
            if key in _seen:
                continue
            _seen[key] = now
        loc = _val(e, "location") or {}
        co = loc.get("coordinates") or [None, None]
        name = _val(e, "name") or eid.rsplit(":", 1)[-1]
        item = {"id": eid.rsplit(":", 1)[-1], "name": name, "lon": co[0], "lat": co[1], "status": "approved",
                "ts": st.get("observedAt") or datetime.now(TZ).isoformat(),
                "title_en": f"Subscription fired: {name} approved Christmas Eve hours",
                "subscription": note.get("subscriptionId")}
        _recent.append(item)
        del _recent[:-50]
        log.info("city notify: %s approved (subscription %s), pushing SSE store to %d client(s)",
                 eid, note.get("subscriptionId"), len(_queues))
        try:
            asyncio.get_running_loop()
            _push(item)
        except RuntimeError:  # called from a thread (the fallback broker delivers in-process)
            if _loop is not None and _loop.is_running():
                _loop.call_soon_threadsafe(_push, item)
        try:
            from kaiku import events
            from kaiku.schema import Event
            events.emit(Event(step="broker", business_id=item["id"], title_en=item["title_en"],
                              title_fi=f"Tilaus laukesi: {name} hyväksyi jouluaaton aukioloajat",
                              detail={"entity": eid, "lon": co[0], "lat": co[1], "observedAt": st.get("observedAt"),
                                      "subscription": note.get("subscriptionId"), "source": "city"}))
        except Exception as ex:  # noqa: BLE001
            log.info("city event emit skipped: %s", ex)
        out.append(item)
    return out


@router.post("/city/notify")
async def notify(request: Request):
    try:
        note = await request.json()
    except ValueError:
        return Response(status_code=204)
    handle_notification(note)
    return Response(status_code=204)


# ------------------------------------------------------------------ subscription + room write
def ensure_subscription(http: httpx.Client | None = None) -> str:
    """Idempotent by subscriptionName. If the stored endpoint differs (a test server made it), recreate it for us."""
    from kaiku.broker import get_broker
    br = get_broker()
    if getattr(br, "using_fallback", False):
        return br.create_subscription(SUB_NAME, ["holidayHoursStatus"], handle_notification)
    own = http is None
    http = http or httpx.Client(timeout=4)
    want = notify_url()
    h = {"Content-Type": "application/json", "Link": LINK}
    try:
        r = http.get(f"{ng()}/subscriptions", params={"limit": 1000}, headers={"Accept": "application/json"})
        r.raise_for_status()
        for s in r.json():
            if s.get("subscriptionName") != SUB_NAME:
                continue
            uri = ((s.get("notification") or {}).get("endpoint") or {}).get("uri")
            if uri == want and s.get("isActive", True) is not False and s.get("status") != "paused":
                return s["id"]
            http.delete(f"{ng()}/subscriptions/{s['id']}")
            log.info("city subscription endpoint %s -> %s: recreated", uri, want)
        body = {"type": "Subscription", "subscriptionName": SUB_NAME, "entities": [{"type": "Store"}],
                "watchedAttributes": ["holidayHoursStatus"],
                "description": "Kaiku /city: a Turku Store's Christmas Eve status changed",
                "notification": {"format": "normalized", "attributes": NOTIFY_ATTRS,
                                 "endpoint": {"uri": want, "accept": "application/json"}}}
        r = http.post(f"{ng()}/subscriptions", json=body, headers=h)
        r.raise_for_status()
        sid = r.headers.get("Location", "").rsplit("/", 1)[-1]
        log.info("city subscription %s -> %s", sid, want)
        return sid
    finally:
        if own:
            http.close()


def write_answer(bid: str, answer: dict, holiday: str = HOLIDAY) -> str:
    """The owner's room answer -> broker: holidayHours default instance + holidayHoursStatus approved (via room).
    Raises on failure; the caller logs 'broker write skipped' and the room answer still succeeds."""
    from kaiku.broker import get_broker
    br = get_broker()
    eid = f"urn:ngsi-ld:Store:{bid}"
    if not bid.startswith("osm-"):
        raise ValueError(f"not a city Store: {bid}")
    if br.get_entity(eid) is None:  # the fallback broker starts empty; Orion has it from the seed
        from kaiku.map import room
        b = room.by_id(bid)
        if not b:
            raise ValueError(f"unknown business {bid}")
        br.upsert_entity(seed_mod.build_entity(b))
    br.set_default(eid, "holidayHours", {"date": holiday, "hours": parse_hours(answer)})
    br.set_status(eid, "holidayHoursStatus", {"date": holiday, "status": "approved", "via": "room"})
    return br.name


def startup() -> dict:
    """Lifespan hook: seed the Stores (only missing ones) and the subscription. Never raises."""
    out = {}
    try:
        out["seed"] = seed_mod.seed()
    except Exception as e:  # noqa: BLE001
        out["seed"] = {"ok": False, "error": str(e)[:120]}
    try:
        out["subscription"] = ensure_subscription()
    except Exception as e:  # noqa: BLE001
        log.warning("city subscription setup failed: %s", e)
        out["subscription"] = None
    return out
