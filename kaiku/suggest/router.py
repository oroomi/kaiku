"""GET /api/feed/{business_id}?date=YYYY-MM-DD  ->  build_feed(). Machine-readable, stable field names."""
from __future__ import annotations

import time
import datetime as _dt

from fastapi import APIRouter, HTTPException, Query

from kaiku.suggest import feed

router = APIRouter()
_cache: dict = {}
TTL = 30.0


@router.get("/api/feed/{business_id}")
def api_feed(business_id: str, date: str | None = Query(None), network: int = Query(1)):
    d = None
    if date:
        try:
            d = _dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
    key = (business_id, d, network)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    res = feed.build_feed(business_id, d, use_network=bool(network))
    if res.get("error"):
        raise HTTPException(404, res["error"])
    _cache[key] = (time.time(), res)
    return res
