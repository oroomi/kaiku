"""/fiware: an open, read-only page for the FIWARE judge.

Everything the page shows is read from the broker (or the events store) when it loads. The proxy below can only GET
entities whose id starts with urn:ngsi-ld: and only a short list of attributes; nothing here can write to the broker.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from kaiku.broker.client import LINK, broker_url
from kaiku.broker.models import CORE_CONTEXT, DS, SDM_CONTEXT, SOURCES, source_of

log = logging.getLogger("kaiku.fiware")
router = APIRouter()

ENTITY_ID = "urn:ngsi-ld:Store:furry-paw"
ALLOWED_ATTRS = ("holidayHours", "holidayHoursStatus", "name", "address", "location", "openingHoursSpecification",
                 "category", "url")
ID_RE = re.compile(r"^urn:ngsi-ld:[A-Za-z0-9_.:\-]{1,160}$")
TIMEOUT = 3.0


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ---- the only places that talk to the broker. Both are GET. Tests replace them with a fake broker.
async def _orion_get(path: str, params: dict | None = None) -> tuple[int, object]:
    """GET {broker}/ngsi-ld/v1{path}. Raises httpx.HTTPError when the broker is unreachable."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{broker_url()}/ngsi-ld/v1{path}", params=params,
                        headers={"Accept": "application/json", "Link": LINK})
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body


async def _orion_version() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            return (await c.get(f"{broker_url()}/version")).json().get("orionld version")
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _fallback_entity(eid: str) -> dict | None:
    """The in-memory fallback's view of the entity (what the chain uses while the broker is down). None if it has none."""
    from kaiku.broker import get_broker
    try:
        return get_broker().get_entity(eid)
    except Exception as e:  # noqa: BLE001
        log.info("fallback read failed: %s", e)
        return None


def _as_list(v) -> list:
    return v if isinstance(v, list) else ([v] if v else [])


def _trim_entity(e: dict, attrs: list[str]) -> dict:
    keep = {"id", "type", *attrs}
    return {k: v for k, v in e.items() if k in keep}


def instances_view(e: dict | None) -> list[dict]:
    """holidayHours instances as table rows: source, datasetId, value text, observedAt, is_default."""
    rows = []
    for i in _as_list((e or {}).get("holidayHours")):
        if not isinstance(i, dict):
            continue
        v = i.get("value") or {}
        h = v.get("hours") if isinstance(v, dict) else None
        if h == "closed":
            txt = "closed"
        elif isinstance(h, list) and h:
            txt = ", ".join(f"{s.get('start')}-{s.get('end')}" for s in h if isinstance(s, dict))
        elif h == "unknown":
            txt = "unknown (this source has no opinion)"
        else:
            txt = "no data"
        ds = i.get("datasetId")
        rows.append({"source": source_of(ds), "datasetId": ds, "date": v.get("date") if isinstance(v, dict) else None,
                     "hours": txt, "note": v.get("note") if isinstance(v, dict) else None,
                     "observedAt": i.get("observedAt"), "is_default": not ds})
    order = {s: n for n, s in enumerate(("default",) + SOURCES)}
    rows.sort(key=lambda r: order.get(r["source"], 99))
    return rows


# ---- pages and API
@router.get("/fiware", response_class=HTMLResponse)
def fiware_page(request: Request):
    from kaiku.app import render
    return render(request, "fiware.html", entity_id=ENTITY_ID, sdm_context=SDM_CONTEXT, core_context=CORE_CONTEXT,
                  dataset_prefix=DS, sources=SOURCES, attrs=",".join(ALLOWED_ATTRS))


@router.get("/api/fiware/entity")
async def entity(id: str = ENTITY_ID, attrs: str = "holidayHours,holidayHoursStatus,name"):
    """Read-only proxy: GET one entity from the broker. Only ids starting with urn:ngsi-ld: and a short attrs list."""
    if not id.startswith("urn:ngsi-ld:") or not ID_RE.match(id):
        raise HTTPException(400, "only ids starting with urn:ngsi-ld: are allowed")
    want = [a for a in (x.strip() for x in attrs.split(",")) if a]
    bad = [a for a in want if a not in ALLOWED_ATTRS]
    if bad or not want:
        raise HTTPException(400, f"attrs must be a subset of: {', '.join(ALLOWED_ATTRS)}")
    base = {"id": id, "read_at": now_utc(), "attrs": want}
    try:
        code, body = await _orion_get(f"/entities/{id}", {"attrs": ",".join(want)})
    except httpx.HTTPError:
        fb = _fallback_entity(id)
        return {**base, "source": "fallback", "broker_offline": True,
                "message": "broker offline, fallback store in use",
                "entity": _trim_entity(fb, want) if fb else None,
                "instances": instances_view(fb) if fb else []}
    if code == 404:
        return {**base, "source": "orion-ld", "broker_offline": False, "entity": None, "instances": [],
                "message": "the broker has no such entity (nothing is shown instead of a guess)"}
    if code != 200 or not isinstance(body, dict):
        raise HTTPException(502, f"broker answered {code}")
    return {**base, "source": "orion-ld", "broker_offline": False, "entity": _trim_entity(body, want),
            "instances": instances_view(body), "message": ""}


@router.get("/api/fiware/subscriptions")
async def subscriptions():
    """The broker's subscriptions, trimmed to what a judge needs."""
    base = {"read_at": now_utc()}
    try:
        code, body = await _orion_get("/subscriptions")
    except httpx.HTTPError:
        return {**base, "broker_offline": True, "message": "broker offline, fallback store in use", "items": []}
    if code != 200 or not isinstance(body, list):
        raise HTTPException(502, f"broker answered {code}")
    items = []
    for s in body:
        n = s.get("notification") or {}
        items.append({"name": s.get("subscriptionName") or s.get("id"), "watched": s.get("watchedAttributes") or [],
                      "endpoint": ((n.get("endpoint") or {}).get("uri")), "status": s.get("status") or ("active" if s.get("isActive") else "paused")})
    return {**base, "broker_offline": False, "message": "", "items": items}


@router.get("/api/fiware/events")
def broker_events(request: Request, limit: int = 10):
    """Last broker-step events (Subscription fired, Proposal written, Decision written), newest last."""
    from kaiku import events, store
    limit = max(1, min(limit, 25))
    evs = [e for e in store.recent_events(200) if e.step == "broker"][:limit]
    evs.reverse()
    return {"read_at": now_utc(), "items": [events.public_view(json.loads(e.model_dump_json()), request) for e in evs]}


@router.get("/api/fiware/mcp")
async def mcp_proof():
    """ngsi-ld-mcp: the tool list the public /mcp endpoint serves, and one live read-only call (query_entities)."""
    out = {"read_at": now_utc(), "tools": [], "example": None, "error": None}
    try:
        from ngsi_ld_mcp.config import Config
        from ngsi_ld_mcp.core import Gateway
        from ngsi_ld_mcp.server import build_server
        cfg = Config(url=broker_url(), hide_decisions=True, context=SDM_CONTEXT)
        srv = build_server(None, cfg, streamable_path="/", open_hosts=True)
        for t in await srv.list_tools():
            ann = t.annotations
            out["tools"].append({"name": t.name, "read_only": bool(ann and ann.readOnlyHint),
                                 "about": (t.description or "").strip().split("\n")[0]})
    except Exception as e:  # noqa: BLE001
        out["error"] = f"ngsi-ld-mcp not available: {type(e).__name__}"
        return out
    call = {"tool": "query_entities", "arguments": {"type": "Store", "attrs": "holidayHours", "limit": 5}}
    out["call"] = call
    try:
        out["example"] = await Gateway(cfg).query_entities(**call["arguments"])
    except Exception as e:  # noqa: BLE001
        out["error"] = f"broker offline, no example call: {type(e).__name__}"
    return out
