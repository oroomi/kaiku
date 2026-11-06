"""Business -> NGSI-LD "Store" entity (Smart Data Models dataModel.PointOfInterest/Store).

Business mirrors the contract in CLAUDE.md (kaiku/schema.py is owned by core and may not exist
in this worktree, so we do not import it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

SDM_CONTEXT = "https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld"
CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
CONTEXT = [SDM_CONTEXT, CORE_CONTEXT]

DS = "urn:ngsi-ld:dataset:kaiku:"
SOURCES = ("lastyear", "website", "google", "peers", "proposed", "owner")


def dataset_id(source: str) -> str:
    return source if source.startswith("urn:") else DS + source


def source_of(dataset: str | None) -> str:
    """'urn:ngsi-ld:dataset:kaiku:google' -> 'google'; None -> 'default' (the resolved truth)."""
    if not dataset:
        return "default"
    return dataset[len(DS):] if dataset.startswith(DS) else dataset


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@dataclass
class Business:
    id: str
    name: str
    address: str = ""
    city: str = ""
    lat: float = 0.0
    lon: float = 0.0
    category: str = ""
    regular_hours: dict = field(default_factory=dict)
    last_year_exceptions: list = field(default_factory=list)
    website: str = ""
    owner_whatsapp: str = ""
    source: str = ""


def entity_id(business_id: str) -> str:
    return business_id if business_id.startswith("urn:") else f"urn:ngsi-ld:Store:{business_id}"


def hours_value(date: str, hours) -> dict:
    """Value of one holidayHours instance: {date, hours: [{start,end}] | "closed"}."""
    return {"date": date, "hours": hours}


def prop(value, dataset: str | None = None, observed_at: str | None = None) -> dict:
    p = {"type": "Property", "value": value}
    if dataset:
        p["datasetId"] = dataset_id(dataset)
    if observed_at:
        p["observedAt"] = observed_at
    return p


_DAYS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
         "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


def opening_hours_spec(regular_hours: dict) -> list:
    """schema.org OpeningHoursSpecification objects; closed days are left out."""
    out = []
    for k, slots in regular_hours.items():
        for s in slots or []:
            out.append({"dayOfWeek": f"https://schema.org/{_DAYS[k]}", "opens": s["start"], "closes": s["end"]})
    return out


def business_to_entity(b: Business, instances: dict | None = None, status: dict | None = None) -> dict:
    """NGSI-LD Store. instances: {source: (value, observed_at)} for holidayHours (one datasetId each);
    source 'default' becomes the instance without datasetId. status: {date, status}."""
    e = {
        "id": entity_id(b.id),
        "type": "Store",
        "name": prop(b.name),
        "address": prop({"type": "PostalAddress", "streetAddress": b.address, "addressLocality": b.city,
                        "addressCountry": "FI"}),
        "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [b.lon, b.lat]}},
        "openingHoursSpecification": prop(opening_hours_spec(b.regular_hours)),
        "category": prop([b.category] if b.category else []),
    }
    if b.website:
        e["url"] = prop(b.website)
    if instances:
        lst = []
        for src, (val, obs) in instances.items():
            lst.append(prop(val, None if src == "default" else src, obs))
        e["holidayHours"] = lst
    if status:
        e["holidayHoursStatus"] = prop(status, observed_at=now_iso())
    return e


def furry_paw() -> Business:
    """Fictional demo business (labelled as such in the UI; Yext sandbox entity SinceAI07)."""
    return Business(
        id="furry-paw", name="Furry Paw Vet Clinic (fictional sandbox)", address="Sample street 1",
        city="Vantaa", lat=60.2934, lon=25.0378, category="veterinary",
        regular_hours={"mon": [{"start": "09:00", "end": "17:00"}], "tue": [{"start": "09:00", "end": "17:00"}],
                       "wed": [{"start": "09:00", "end": "17:00"}], "thu": [{"start": "09:00", "end": "17:00"}],
                       "fri": [{"start": "09:00", "end": "16:00"}], "sat": [], "sun": []},
        source="sample")
