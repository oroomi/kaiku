"""Turku centre businesses from OpenStreetMap (Overpass), cached to data/turku_businesses.json.

Data: OpenStreetMap contributors, ODbL. If every mirror fails we write a clearly labelled fictional placeholder set.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

CENTER = (60.4518, 22.2666)
RADIUS_M = 1500
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
SOURCE = "OpenStreetMap contributors, ODbL"
CAT_FI = {"cafe": "Kahvila", "restaurant": "Ravintola", "fast_food": "Pikaruoka", "bar": "Baari", "pub": "Pubi",
          "pharmacy": "Apteekki", "veterinary": "Eläinlääkäri", "gym": "Kuntosali", "hairdresser": "Kampaamo",
          "clothes": "Vaateliike", "bakery": "Leipomo", "books": "Kirjakauppa", "florist": "Kukkakauppa",
          "supermarket": "Päivittäistavarakauppa", "convenience": "Lähikauppa", "shop": "Liike",
          "dentist": "Hammaslääkäri", "doctors": "Lääkäriasema", "beauty": "Kauneushoitola"}
QUERY_TAGS = [("amenity", "cafe|restaurant|fast_food|bar|pub|pharmacy|veterinary|dentist|doctors"),
              ("shop", "hairdresser|beauty|clothes|bakery|books|florist|supermarket|convenience|gift|shoes|jewelry|optician|sports|electronics|variety_store"),
              ("leisure", "fitness_centre"), ("healthcare", "dentist|doctor|physiotherapist|clinic")]


def data_dir() -> Path:
    from kaiku.config import settings
    return Path(os.getenv("KAIKU_DATA_DIR") or settings.DATA_DIR)


def cache_path() -> Path:
    return data_dir() / "turku_businesses.json"


def build_query() -> str:
    lat, lon = CENTER
    parts = []
    for k, v in QUERY_TAGS:
        for t in ("node", "way"):
            parts.append(f'{t}["{k}"~"^({v})$"]["name"](around:{RADIUS_M},{lat},{lon});')
    return "[out:json][timeout:50];(" + "".join(parts) + ");out center tags;"


def _category(tags: dict) -> str:
    if tags.get("leisure") == "fitness_centre":
        return "gym"
    for k in ("amenity", "shop", "healthcare"):
        if tags.get(k):
            return {"doctor": "doctors", "clinic": "doctors"}.get(tags[k], tags[k])
    return "shop"


def _address(tags: dict) -> str:
    s, n = tags.get("addr:street"), tags.get("addr:housenumber")
    return f"{s} {n}".strip() if s and n else (s or "")


def has_holiday_rule(opening_hours: str | None, month: int = 12, day: int = 24) -> bool:
    """True only if the OSM opening_hours text mentions Dec 24 explicitly (e.g. 'Dec 24 off')."""
    if not opening_hours:
        return False
    return bool(re.search(r"\bDec\s*(24|1-31|\d+\s*-\s*\d*24)", opening_hours))


def parse(raw: dict) -> list[dict]:
    out, seen = [], set()
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not name or lat is None or lon is None:
            continue
        key = (name.lower(), round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        oh = tags.get("opening_hours")
        b = {"id": f"osm-{el['type'][0]}{el['id']}", "osm_id": f"{el['type']}/{el['id']}", "name": name,
             "category": _category(tags), "lat": round(lat, 6), "lon": round(lon, 6),
             "address": _address(tags), "label": "real"}
        if oh:
            b["opening_hours"] = oh
        if tags.get("website") or tags.get("contact:website"):
            b["website"] = tags.get("website") or tags.get("contact:website")
        b["holiday_hours_found"] = has_holiday_rule(oh)
        out.append(b)
    out.sort(key=lambda b: (round(b["lat"], 3), b["lon"]))
    return out


def fetch_overpass(mirrors=None, timeout=60, retries=3, sleep=time.sleep):
    q, mirrors = build_query(), mirrors or MIRRORS
    errors = []
    for url in mirrors:
        for i in range(retries):
            try:
                r = httpx.post(url, data={"data": q}, timeout=timeout,
                               headers={"User-Agent": "kaiku-hackathon/1.0 (Since AI 2026)"})
                if r.status_code == 200 and r.json().get("elements") is not None:
                    return url, r.json()
                errors.append(f"{url} HTTP {r.status_code}")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{url} {type(e).__name__}")
            sleep(2 ** i)
    raise RuntimeError("; ".join(errors[-6:]))


STREETS = [("Yliopistonkatu", 60.4500, 22.2680, 60.4535, 22.2700), ("Aurakatu", 60.4510, 22.2650, 60.4480, 22.2700),
           ("Kauppiaskatu", 60.4515, 22.2640, 60.4520, 22.2690), ("Eerikinkatu", 60.4490, 22.2600, 60.4505, 22.2690),
           ("Humalistonkatu", 60.4540, 22.2640, 60.4525, 22.2700), ("Linnankatu", 60.4350, 22.2290, 60.4505, 22.2790)]


def fallback_set(n: int = 40) -> list[dict]:
    """Fictional placeholder points on the lines of real Turku streets. Names are numbered, never real shops."""
    kinds = ["cafe", "restaurant", "hairdresser", "pharmacy", "veterinary", "gym", "clothes", "bakery"]
    out = []
    for i in range(n):
        st, a0, o0, a1, o1 = STREETS[i % len(STREETS)]
        t = ((i // len(STREETS)) + 0.5) / math.ceil(n / len(STREETS))
        k = kinds[i % len(kinds)]
        out.append({"id": f"fict-{i+1}", "osm_id": None, "name": f"{CAT_FI.get(k, 'Liike')} {i+1}", "category": k,
                    "lat": round(a0 + (a1 - a0) * t, 6), "lon": round(o0 + (o1 - o0) * t, 6),
                    "address": f"{st} {10 + (i * 3) % 40}", "label": "fictional placeholder",
                    "holiday_hours_found": False})
    return out


def build_cache(path: Path | None = None, **kw) -> dict:
    path = path or cache_path()
    try:
        mirror, raw = fetch_overpass(**kw)
        items = parse(raw)
        if len(items) < 20:
            raise RuntimeError(f"only {len(items)} named businesses")
        doc = {"source": SOURCE, "mirror": mirror, "label": "real", "fallback": False}
    except Exception as e:  # noqa: BLE001
        items = fallback_set()
        doc = {"source": "none, offline", "mirror": None, "label": "fictional placeholder", "fallback": True,
               "error": str(e)[:300]}
    doc.update({"fetched_at": datetime.now(timezone.utc).isoformat(), "center": list(CENTER), "radius_m": RADIUS_M,
                "count": len(items), "businesses": items})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=0))
    tmp.replace(path)
    return doc


def load(path: Path | None = None) -> dict:
    path = path or cache_path()
    if not path.exists():
        src = Path(__file__).resolve().parents[2] / "data" / "turku_businesses.json"
        if src.exists() and src != path:
            return json.loads(src.read_text())
        return build_cache(path)
    return json.loads(path.read_text())


if __name__ == "__main__":
    d = build_cache()
    print(d["count"], d["mirror"], d.get("error", ""))
