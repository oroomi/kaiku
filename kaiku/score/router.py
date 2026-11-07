"""GET /api/score/{business_id}: the listing score. See docs/score.md."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..chat import feed as F
from ..listing import router as L
from . import engine

router = APIRouter()


@router.get("/api/score/{business_id}")
def api_score(business_id: str, fresh: int = Query(0), quick: int = Query(0)):
    try:
        listing = L.read_listing(business_id, bool(fresh))
    except KeyError:
        raise HTTPException(404, "unknown business")
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    feed = F.get_feed(business_id, network=not quick)
    try:
        from ..learn import timetravel
        today = timetravel.today().isoformat()
    except Exception:
        today = None
    return engine.compute(listing, feed, today=today)
