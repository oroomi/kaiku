"""GET /api/listing/{business_id}: the Yext sandbox entity exactly as Connect publishes it today, normalised.

Thin: one read through the existing apply client (kaiku.apply.yext.YextSandbox), cached 30 s. Nothing is invented:
a field the entity does not have is None, and the page says "no data" for it.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..chat.util import hours_text

router = APIRouter()
TTL = 30.0
DAYS = [("mon", "monday"), ("tue", "tuesday"), ("wed", "wednesday"), ("thu", "thursday"),
        ("fri", "friday"), ("sat", "saturday"), ("sun", "sunday")]
_cache: dict = {}
_lock = threading.Lock()


def _client():
    """The one Yext client: the apply module's. Tests replace this."""
    from ..apply.yext import YextSandbox
    return YextSandbox()


def entity_id_for(business_id: str) -> str | None:
    from .. import store
    if store.get_business(business_id) is None:
        return None
    from ..config import settings
    return settings.YEXT_ENTITY_ID


def invalidate(business_id: str | None = None) -> None:
    with _lock:
        if business_id is None:
            _cache.clear()
        else:
            _cache.pop(business_id, None)


def _day(h: dict | None):
    """Yext day -> [{start,end}] | 'closed' | None (no data)."""
    if not h:
        return None
    if h.get("isClosed"):
        return "closed"
    iv = h.get("openIntervals") or []
    return [{"start": x["start"], "end": x["end"]} for x in iv if x.get("start") and x.get("end")] or None


def _url(v) -> str | None:
    if isinstance(v, dict):
        v = v.get("url") or v.get("displayUrl")
    v = (v or "").strip() if isinstance(v, str) else ""
    return v or None


def normalise(ent: dict, reviews: dict | None, read_at: str | None = None) -> dict:
    a = ent.get("address") or {}
    addr = None
    if a.get("line1") or a.get("city"):
        text = ", ".join(x for x in [a.get("line1"), " ".join(x for x in [a.get("postalCode"), a.get("city")] if x)] if x)
        addr = {"line1": a.get("line1"), "postal_code": a.get("postalCode"), "city": a.get("city"),
                "country": a.get("countryCode"), "text": text}
    cats = ent.get("categories") or {}
    cat_list: list[str] = []
    for v in cats.values() if isinstance(cats, dict) else []:
        cat_list += [str(x) for x in (v if isinstance(v, list) else [v]) if x]
    hours = ent.get("hours") or {}
    regular = {k: _day(hours.get(full)) for k, full in DAYS}
    rows = []
    for r in sorted(hours.get("holidayHours") or [], key=lambda r: r.get("date", "")):
        v = "closed" if r.get("isClosed") else [{"start": x["start"], "end": x["end"]} for x in r.get("openIntervals") or []]
        rows.append({"date": r["date"], "hours": v or "closed", "text": hours_text(v or "closed")})
    rev = None
    if isinstance(reviews, dict):
        n = int(reviews.get("count") or 0)
        avg = reviews.get("averageRating")
        rev = {"count": n, "average": round(float(avg), 1) if n and avg else None}
    desc = (ent.get("description") or "").strip()
    return {
        "entity_id": (ent.get("meta") or {}).get("id"), "name": ent.get("name") or None, "address": addr, "categories": cat_list,
        "phone": (ent.get("mainPhone") or "").strip() or None, "website": _url(ent.get("websiteUrl")),
        "hours": regular, "hours_text": {k: (hours_text(v) if v else None) for k, v in regular.items()},
        "holiday_hours": rows, "description": desc or None, "reviews": rev,
        "read_at": read_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def read_listing(business_id: str, fresh: bool = False) -> dict:
    """The normalised entity. Raises KeyError (unknown business) or RuntimeError (Yext not reachable)."""
    eid = entity_id_for(business_id)
    if eid is None:
        raise KeyError(business_id)
    with _lock:
        hit = _cache.get(business_id)
        if hit and not fresh and time.time() - hit[0] < TTL:
            return hit[1]
    try:
        c = _client()
        ent = c.get_entity(eid)
    except Exception as exc:
        raise RuntimeError(f"Yext sandbox not reachable ({type(exc).__name__})") from None
    try:
        reviews = c._req("GET", "/reviews")
    except Exception:
        reviews = None   # no review data is "no data", not "no reviews"
    out = normalise(ent, reviews)
    out["business_id"] = business_id
    with _lock:
        _cache[business_id] = (time.time(), out)
    return out


@router.get("/api/listing/{business_id}")
def api_listing(business_id: str, fresh: int = Query(0)):
    try:
        return read_listing(business_id, bool(fresh))
    except KeyError:
        raise HTTPException(404, "unknown business")
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
