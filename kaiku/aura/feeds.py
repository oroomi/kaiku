"""Aura: fetchers for the three open feeds. Each returns parsed records; errors propagate to the feeder."""
from __future__ import annotations

import time

import httpx

from . import models

FOLI_URL = "https://data.foli.fi/siri/vm"
AIS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations?radius=30&latitude=60.45&longitude=22.2"
VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"
WX_URL = "https://api.open-meteo.com/v1/forecast?latitude=60.45&longitude=22.27&current=temperature_2m,wind_speed_10m,weather_code,precipitation"
AIS_HEADERS = {"Accept-Encoding": "gzip", "Digitraffic-User": "Kaiku-Aura/1.0 (hackathon)"}

_names: dict = {"at": 0.0, "map": {}}


async def fetch_foli(http: httpx.AsyncClient) -> list[dict]:
    r = await http.get(FOLI_URL, timeout=15)
    r.raise_for_status()
    return models.parse_foli(r.json())


async def vessel_names(http: httpx.AsyncClient) -> dict:
    if time.time() - _names["at"] > 3600 or not _names["map"]:
        r = await http.get(VESSELS_URL, headers=AIS_HEADERS, timeout=30)
        r.raise_for_status()
        _names["map"] = {str(v["mmsi"]): v.get("name", "").strip() for v in r.json() if v.get("name")}
        _names["at"] = time.time()
    return _names["map"]


async def fetch_ais(http: httpx.AsyncClient) -> list[dict]:
    r = await http.get(AIS_URL, headers=AIS_HEADERS, timeout=20)
    r.raise_for_status()
    try:
        names = await vessel_names(http)
    except httpx.HTTPError:
        names = _names["map"]
    return models.parse_ais(r.json(), names)


async def fetch_weather(http: httpx.AsyncClient) -> dict | None:
    r = await http.get(WX_URL, timeout=15)
    r.raise_for_status()
    return models.parse_weather(r.json())
