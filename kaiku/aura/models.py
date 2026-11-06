"""Aura: feed records to NGSI-LD entities (Smart Data Models) and back to compact map records."""
from __future__ import annotations

import math
from datetime import datetime, timezone

SDM_TRANSPORT = "https://raw.githubusercontent.com/smart-data-models/dataModel.Transportation/master/context.jsonld"
SDM_WEATHER = "https://raw.githubusercontent.com/smart-data-models/dataModel.Weather/master/context.jsonld"
CORE_CTX = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"


AURA_NS = "https://themishakingroup.com/aura/ns#"
AURA_CTX = {k: AURA_NS + k for k in ("lineRef", "destination", "delay", "nextStop", "mmsi")}
KNOT_KMH = 1.852


def link(ctx: str) -> str:
    return f'<{ctx}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'


SRC_FOLI = "Föli, data.foli.fi/siri/vm, CC BY 4.0"
SRC_AIS = "Fintraffic Digitraffic, meri.digitraffic.fi AIS, CC BY 4.0"
SRC_WX = "Open-Meteo, api.open-meteo.com, CC BY 4.0"

WMO_FI = {0: "selkeää", 1: "enimmäkseen selkeää", 2: "puolipilvistä", 3: "pilvistä", 45: "sumua", 48: "huurtavaa sumua",
          51: "tihkua", 53: "tihkua", 55: "tihkua", 61: "vesisadetta", 63: "vesisadetta", 65: "kovaa vesisadetta",
          71: "lumisadetta", 73: "lumisadetta", 75: "kovaa lumisadetta", 80: "kuuroja", 81: "kuuroja", 82: "kovia kuuroja",
          95: "ukkosta"}
WMO_EN = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "rime fog", 51: "drizzle",
          53: "drizzle", 55: "drizzle", 61: "rain", 63: "rain", 65: "heavy rain", 71: "snow", 73: "snow", 75: "heavy snow",
          80: "showers", 81: "showers", 82: "heavy showers", 95: "thunderstorm"}


def iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else datetime.now(timezone.utc).timestamp(), timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def bearing(lon1, lat1, lon2, lat2) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------- parsers
def parse_foli(raw: dict) -> list[dict]:
    out = []
    for ref, v in ((raw.get("result") or {}).get("vehicles") or {}).items():
        if v.get("latitude") is None or v.get("longitude") is None:
            continue
        out.append({"ref": str(v.get("vehicleref") or ref), "line": str(v.get("publishedlinename") or v.get("lineref") or ""),
                    "lon": float(v["longitude"]), "lat": float(v["latitude"]), "bearing": v.get("bearing"),
                    "delay_s": v.get("delaysecs"), "dest": v.get("destinationname") or v.get("next_destinationdisplay") or "",
                    "next_stop": v.get("next_stoppointname") or "", "ts": v.get("recordedattime")})
    return out


def parse_ais(raw: dict, names: dict | None = None) -> list[dict]:
    names = names or {}
    out = []
    for f in raw.get("features") or []:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        c = g.get("coordinates")
        if not c or len(c) < 2:
            continue
        mmsi = str(f.get("mmsi") or p.get("mmsi"))
        hd = p.get("heading")
        if hd is None or hd == 511:
            hd = p.get("cog") if p.get("cog") not in (None, 360.0) else None
        ts = p.get("timestampExternal")
        out.append({"mmsi": mmsi, "name": names.get(mmsi, ""), "lon": float(c[0]), "lat": float(c[1]), "heading": hd,
                    "sog": p.get("sog"), "ts": ts / 1000 if ts else None})
    return out


def parse_weather(raw: dict) -> dict | None:
    c = raw.get("current")
    if not c:
        return None
    return {"temp": c.get("temperature_2m"), "wind_kmh": c.get("wind_speed_10m"), "code": c.get("weather_code"),
            "precip": c.get("precipitation"), "time": c.get("time")}


# ---------------------------------------------------------------- NGSI-LD entities
def _prop(v, observed=None, unit=None):
    p = {"type": "Property", "value": v}
    if unit:
        p["unitCode"] = unit
    if observed:
        p["observedAt"] = observed
    return p


def _geo(lon, lat, observed):
    return {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}, "observedAt": observed}


def _motion(e: dict, speed_kmh: float | None, heading: float | None, now: str) -> None:
    """SDM Vehicle: speed in km/h (-1 = unknown); heading 0..359, and -1 when stationary (speed 0)."""
    if speed_kmh is None:
        e["speed"] = _prop(-1, now, "KMH")
    else:
        e["speed"] = _prop(round(max(speed_kmh, 0.0), 1), now, "KMH")
        if speed_kmh <= 0:
            e["heading"] = _prop(-1, now, "DD")
            return
    if heading is not None:
        e["heading"] = _prop(int(round(heading)) % 360, now, "DD")


def bus_entity(b: dict, heading: float | None, now: str, speed_kmh: float | None = None) -> dict:
    e = {"@context": [SDM_TRANSPORT, AURA_CTX],
         "id": f"urn:ngsi-ld:Vehicle:foli:{b['ref']}", "type": "Vehicle",
         "vehicleType": _prop("bus"), "category": _prop(["public", "tracked"]),
         "name": _prop(f"Linja {b['line']}" if b["line"] else f"Bus {b['ref']}"),
         "location": _geo(b["lon"], b["lat"], now),
         "lineRef": _prop(b["line"]), "destination": _prop(b["dest"]),
         "source": _prop(SRC_FOLI, now)}
    _motion(e, speed_kmh, heading, now)
    if b.get("delay_s") is not None:
        e["delay"] = _prop(b["delay_s"], now, "SEC")
    if b.get("next_stop"):
        e["nextStop"] = _prop(b["next_stop"])
    return e


def ship_entity(s: dict, now: str) -> dict:
    # SDM vehicleType has "vessel"; category: AIS-tracked, no claim about private or public service
    e = {"@context": [SDM_TRANSPORT, AURA_CTX],
         "id": f"urn:ngsi-ld:Vehicle:ais:{s['mmsi']}", "type": "Vehicle",
         "vehicleType": _prop("vessel"), "category": _prop(["tracked"]), "name": _prop(s["name"] or f"MMSI {s['mmsi']}"),
         "location": _geo(s["lon"], s["lat"], now), "mmsi": _prop(s["mmsi"]), "source": _prop(SRC_AIS, now)}
    sog = s.get("sog")
    kmh = None if sog is None or sog >= 102.3 else sog * KNOT_KMH  # AIS 102.3 kn = "not available"
    _motion(e, kmh, s.get("heading"), now)
    return e


def weather_entity(w: dict, lon=22.27, lat=60.45) -> dict:
    now = iso()
    e = {"id": "urn:ngsi-ld:WeatherObserved:turku", "type": "WeatherObserved",
         "location": _geo(lon, lat, now), "dateObserved": {"type": "Property", "value": {"@type": "DateTime", "@value": now}},
         "temperature": _prop(w["temp"], now, "CEL"), "windSpeed": _prop(round((w["wind_kmh"] or 0) / 3.6, 1), now, "MTS"),
         "precipitation": _prop(w["precip"], now, "MMT"), "weatherType": _prop(WMO_EN.get(w["code"], f"WMO {w['code']}")),
         "source": _prop(SRC_WX, now)}
    return e


# ---------------------------------------------------------------- read side
def _val(e, key):
    """Value of attribute `key`, tolerant to expanded names (…/key or …#key)."""
    for k, v in e.items():
        if k == key or k.rsplit("/", 1)[-1].rsplit("#", 1)[-1] == key:
            return v.get("value") if isinstance(v, dict) else v
    return None


def compact(e: dict) -> dict | None:
    """Entity (normalized) to the small record the map uses."""
    loc = _val(e, "location")
    t = e.get("type", "").rsplit("/", 1)[-1]
    lp = next((v for k, v in e.items() if k.rsplit("/", 1)[-1] == "location"), {}) or {}
    obs = lp.get("observedAt")
    if t == "WeatherObserved":
        return {"id": e["id"], "kind": "weather", "temp": _val(e, "temperature"), "wind_ms": _val(e, "windSpeed"),
                "precip": _val(e, "precipitation"), "wtype": _val(e, "weatherType"), "obs": obs}
    if not loc or "coordinates" not in loc:
        return None
    kind = _val(e, "vehicleType") or "bus"
    kind = "ship" if kind in ("vessel", "ship") else kind
    return {"id": e["id"], "kind": kind, "lon": loc["coordinates"][0], "lat": loc["coordinates"][1],
            "heading": (lambda h: None if h is None or h < 0 else h)(_val(e, "heading")), "name": _val(e, "name"), "line": _val(e, "lineRef"), "dest": _val(e, "destination"),
            "delay": _val(e, "delay"), "obs": obs}


def age_s(obs: str | None) -> float:
    if not obs:
        return 1e9
    try:
        return datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(obs.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 1e9


# ---------------------------------------------------------------- subscriptions
def subscription_body(p: dict, notify_uri: str) -> dict:
    """NGSI-LD Subscription from a stored proposal: geoQ near;maxDistance, watchedAttributes location."""
    ent = {"type": "Vehicle"}
    body = {"type": "Subscription", "subscriptionName": f"aura-{p['id']}", "description": p.get("description_en", ""),
            "entities": [ent], "watchedAttributes": ["location"],
            "geoQ": {"geometry": "Point", "coordinates": [p["geo_center"][0], p["geo_center"][1]],
                     "georel": f"near;maxDistance=={int(p['geo_radius_m'])}"},
            "throttling": 20,
            "notification": {"format": "normalized", "attributes": ["location", "name", "lineRef", "vehicleType", "destination"],
                             "endpoint": {"uri": notify_uri, "accept": "application/json"}}}
    vt = {"bus": "bus", "ship": "vessel", "vessel": "vessel"}.get(p.get("entity_type"))
    if vt:
        body["q"] = f'vehicleType=="{vt}"'
    if p.get("attribute_condition"):
        body["q"] = (body.get("q", "") + (";" if body.get("q") else "") + p["attribute_condition"])
    return body
