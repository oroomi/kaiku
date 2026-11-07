"""813 real Turku businesses (OpenStreetMap, ODbL) -> NGSI-LD Store entities in Orion-LD.

Run by hand: python -m kaiku.city.seed  (add --force to put every status back to its seed value).
Ids: urn:ngsi-ld:Store:osm-<n|w><osm id>. Never touches urn:ngsi-ld:Store:furry-paw.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import httpx

from kaiku.broker.client import LINK, broker_url
from kaiku.broker.models import Business, business_to_entity, prop

log = logging.getLogger("kaiku.city")
ROOT = Path(__file__).resolve().parents[2]
HOLIDAY = "2026-12-24"
SOURCE = "OpenStreetMap contributors, ODbL"
ID_PATTERN = "^urn:ngsi-ld:Store:osm-"
CHUNK = 100


def businesses_path() -> Path:
    try:
        from kaiku.map import osm
        p = osm.cache_path()
        if p.exists():
            return p
    except Exception:  # noqa: BLE001
        pass
    return ROOT / "data" / "turku_businesses.json"


def load_businesses(path: Path | None = None) -> list[dict]:
    raw = json.loads((path or businesses_path()).read_text())
    items = raw if isinstance(raw, list) else raw.get("businesses", [])
    return [b for b in items if b.get("id", "").startswith("osm-") and b.get("lat") is not None and b.get("lon") is not None]


def seed_status(b: dict) -> dict:
    """seed=True tells every notification handler this is the idle start state, not a decision."""
    return {"date": HOLIDAY, "status": "known" if b.get("holiday_hours_found") else "missing", "seed": True}


def build_entity(b: dict) -> dict:
    biz = Business(id=b["id"], name=b.get("name", ""), address=b.get("address") or "", city="Turku",
                   lat=float(b["lat"]), lon=float(b["lon"]), category=b.get("category") or "",
                   website=b.get("website") or "", source="osm")
    e = business_to_entity(biz, status=seed_status(b))
    e.pop("openingHoursSpecification", None)  # OSM opening_hours is free text; we do not parse it into schema.org
    e["source"] = prop(SOURCE)
    return e


def build_entities(items: list[dict] | None = None) -> list[dict]:
    return [build_entity(b) for b in (items if items is not None else load_businesses())]


def _existing(http: httpx.Client, base: str) -> dict:
    """{id: holidayHoursStatus value} for the osm Stores already in the broker."""
    r = http.get(f"{base}/ngsi-ld/v1/entities", params={"type": "Store", "idPattern": ID_PATTERN, "limit": 1000,
                                                       "attrs": "holidayHoursStatus"},
                 headers={"Accept": "application/json", "Link": LINK})
    r.raise_for_status()
    return {e["id"]: (e.get("holidayHoursStatus") or {}).get("value") for e in r.json()}


def _post(http: httpx.Client, base: str, ents: list[dict], update: bool) -> None:
    q = "?options=update" if update else ""
    for i in range(0, len(ents), CHUNK):
        r = http.post(f"{base}/ngsi-ld/v1/entityOperations/upsert{q}", json=ents[i:i + CHUNK],
                      headers={"Content-Type": "application/json", "Link": LINK})
        if r.status_code not in (200, 201, 204):
            raise httpx.HTTPStatusError(f"upsert -> {r.status_code} {r.text[:160]}", request=r.request, response=r)


def seed(force: bool = False, http: httpx.Client | None = None, items: list[dict] | None = None) -> dict:
    """Idempotent. Creates the Stores that are missing; with force=True also puts every Store whose status is not
    its seed value back to the seed state (whole entity replaced, so a room answer's holidayHours goes too).
    Never raises: returns {ok: False, error} when the broker is down."""
    t0 = time.time()
    base = broker_url()
    own = http is None
    http = http or httpx.Client(timeout=10)
    try:
        ents = build_entities(items)
        have = _existing(http, base)
        new = [e for e in ents if e["id"] not in have]
        changed = []
        if force:
            want = {e["id"]: e["holidayHoursStatus"]["value"] for e in ents}
            changed = [e for e in ents if e["id"] in have and have[e["id"]] != want[e["id"]]]
        if new:
            _post(http, base, new, update=True)
        if changed:
            _post(http, base, changed, update=False)  # replace: drops the room's holidayHours instance
        ms = int((time.time() - t0) * 1000)
        out = {"ok": True, "count": len(ents), "created": len(new), "reset": len(changed), "ms": ms}
        log.info("city seed: %d Store entities (created %d, reset %d) in %d ms", len(ents), len(new), len(changed), ms)
        return out
    except Exception as e:  # noqa: BLE001  the broker being down never breaks start-up or reset
        log.warning("city seed skipped: %s", e)
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    finally:
        if own:
            http.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(seed(force="--force" in sys.argv)))
