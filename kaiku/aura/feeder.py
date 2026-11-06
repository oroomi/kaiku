"""Aura feeder: polls Föli, AIS and Open-Meteo and upserts NGSI-LD entities into Orion-LD.
Run: python3 -m kaiku.aura.feeder"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

from . import feeds, models

log = logging.getLogger("aura.feeder")
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "aura_cache" / "latest.json"
BROKER = os.environ.get("KAIKU_BROKER_URL", "http://127.0.0.1:1026").rstrip("/")
NG = BROKER + "/ngsi-ld/v1"
INTERVALS = {"buses": 10, "ships": 20, "weather": 300}
STALE_DELETE_S = 600

state = {"mode": None, "last": {}, "ms": {}, "counts": {}, "seen": {}, "headings": {}, "cache": {"buses": [], "ships": [], "weather": None}}


async def upsert(http: httpx.AsyncClient, entities: list[dict], ctx: str) -> str:
    """Batch upsert without datasetId. Preferred: entityOperations/upsert?options=update.
    If this build rejects it: POST /entities for new ids, PATCH /entities/{id}/attrs for existing."""
    h = {"Content-Type": "application/json", "Link": models.link(ctx)}
    if state["mode"] != "fallback":
        r = await http.post(f"{NG}/entityOperations/upsert?options=update", json=entities, headers=h)
        if r.status_code in (200, 201, 204):
            state["mode"] = "upsert"
            return "upsert"
        log.warning("upsert rejected %s %s, falling back", r.status_code, r.text[:120])
        state["mode"] = "fallback"
    for e in entities:
        r = await http.post(f"{NG}/entities", json=e, headers=h)
        if r.status_code == 409:
            attrs = {k: v for k, v in e.items() if k not in ("id", "type")}
            r = await http.patch(f"{NG}/entities/{e['id']}/attrs", json=attrs, headers=h)
        if r.status_code >= 300:
            log.warning("write %s -> %s %s", e["id"], r.status_code, r.text[:100])
    return "fallback"


def save_cache() -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    doc = {**state["cache"], "polled": state["last"], "saved": models.iso()}
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    tmp.replace(CACHE)


async def cleanup(http: httpx.AsyncClient) -> int:
    now = time.time()
    gone = [i for i, t in state["seen"].items() if now - t > STALE_DELETE_S]
    if gone:
        try:
            await http.post(f"{NG}/entityOperations/delete", json=gone, headers={"Content-Type": "application/json"})
        except httpx.HTTPError:
            return 0
        for i in gone:
            state["seen"].pop(i, None)
    return len(gone)


async def cycle(http: httpx.AsyncClient, kind: str) -> None:
    t0 = time.time()
    now = models.iso()
    try:
        if kind == "buses":
            recs = await feeds.fetch_foli(http)
            ents = []
            for b in recs:
                prev = state["headings"].get(b["ref"])
                hd = b.get("bearing") if isinstance(b.get("bearing"), (int, float)) else None
                if hd is None:
                    hd = prev[2] if prev else None
                    if prev and models.haversine_m(prev[0], prev[1], b["lon"], b["lat"]) > 8:
                        hd = models.bearing(prev[0], prev[1], b["lon"], b["lat"])
                state["headings"][b["ref"]] = (b["lon"], b["lat"], hd)
                ents.append(models.bus_entity(b, hd, now))
            ctx = models.SDM_TRANSPORT
        elif kind == "ships":
            recs = await feeds.fetch_ais(http)
            ents = [models.ship_entity(s, now) for s in recs]
            ctx = models.SDM_TRANSPORT
        else:
            w = await feeds.fetch_weather(http)
            ents = [models.weather_entity(w)] if w else []
            ctx = models.SDM_WEATHER
        t1 = time.time()
        way = "cache-only"
        try:
            if ents:
                way = await upsert(http, ents, ctx)
        except httpx.HTTPError as e:
            log.warning("broker unreachable: %s", e)
            way = "broker-down"
        comp = [c for c in (models.compact(e) for e in ents) if c]
        for e in ents:
            state["seen"][e["id"]] = time.time()
        state["cache"][kind if kind != "weather" else "weather"] = comp[0] if kind == "weather" and comp else (comp if kind != "weather" else None)
        state["last"][kind] = now
        state["counts"][kind] = len(ents)
        save_cache()
        n = await cleanup(http) if kind == "buses" else 0
        log.info("%s n=%d fetch=%dms write=%dms via=%s stale_deleted=%d", kind, len(ents), (t1 - t0) * 1000, (time.time() - t1) * 1000, way, n)
    except Exception as e:  # noqa: BLE001  one failing feed must not stop the loop
        log.warning("%s cycle failed: %s", kind, e)


async def loop(kind: str, http: httpx.AsyncClient) -> None:
    while True:
        await cycle(http, kind)
        await asyncio.sleep(INTERVALS[kind])


async def main() -> None:
    if CACHE.exists():  # seed so a restart keeps the other feeds visible
        try:
            old = json.loads(CACHE.read_text())
            for k in ("buses", "ships", "weather"):
                state["cache"][k] = old.get(k, state["cache"][k])
            state["last"] = old.get("polled", {})
        except ValueError:
            pass
    async with httpx.AsyncClient(timeout=10) as http:
        await asyncio.gather(*(loop(k, http) for k in INTERVALS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
