"""Feed client. Uses kaiku.suggest.feed (the real engine) when it imports, kaiku.chat.feed_stub otherwise."""
from __future__ import annotations

import importlib
import logging
import os
import time

log = logging.getLogger("kaiku.chat.feed")


_TERMINAL = ("approved", "edited", "applied", "declined")


def with_decisions(feed: dict) -> dict:
    """The engine builds every card as 'proposed'. Lay the owner's recorded decisions over a COPY of the feed, so the cards,
    the chat and /api/feed all say what really happened. Only terminal decisions count; a period is decided when all its dates are."""
    try:
        from .. import store
        stored = store.list_suggestions(feed.get("business_id"), 200)
    except Exception:
        return feed
    by_id, by_date = {}, {}
    for s in stored:                      # newest first
        if s.status in _TERMINAL:
            st = "declined" if s.status == "declined" else "approved"   # edited and applied are approvals too
            by_id.setdefault(s.id, st)
            by_date.setdefault(s.holiday_date, st)
    out = []
    for i in feed.get("suggestions", []):
        st = by_id.get(i.get("id")) or by_id.get(i.get("suggestion_id"))
        if not st and i.get("kind") == "holiday_hours":
            st = by_date.get(i.get("holiday_date"))
        if not st and i.get("kind") == "period" and isinstance(i.get("proposed"), list):
            ds = [by_date.get(m.get("date")) for m in i["proposed"] if isinstance(m, dict) and m.get("date")]
            if ds and all(ds):
                st = "approved" if any(d != "declined" for d in ds) else "declined"
        out.append({**i, "status": st} if st else i)
    return {**feed, "suggestions": out}


_cache: dict = {}
TTL = 30.0


def get_feed(business_id: str, network: bool = True) -> dict:
    """network=False skips the slow per-holiday network signals (the first paint); the full feed is cached for 30 s like /api/feed.
    KAIKU_FEED_NETWORK=0 forces network off (the test suite never fetches websites)."""
    if os.environ.get("KAIKU_FEED_NETWORK", "1") == "0":
        network = False
    key = (business_id, network)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return with_decisions(hit[1])
    t0 = time.time()
    res = _get_feed(business_id, network)
    if time.time() - t0 > 1.0:   # only a slow (network) build is worth keeping
        _cache[key] = (time.time(), res)
    return with_decisions(res)


def _get_feed(business_id: str, network: bool = True) -> dict:
    if os.environ.get("KAIKU_FEED_FIXTURE"):  # a fixed feed (tests, screenshots) wins over the engine
        from .feed_stub import get_feed as stub
        return stub(business_id)
    try:
        real = importlib.import_module("kaiku.suggest.feed")  # via sys.modules, so tests can swap or remove it
    except Exception:
        real = None
    if real is not None:
        for name in ("get_feed", "build_feed", "feed_for"):
            fn = getattr(real, name, None)
            if callable(fn):
                try:
                    r = fn(business_id) if network or name != "build_feed" else fn(business_id, use_network=False)
                    if isinstance(r, dict) and "suggestions" in r:
                        return r
                except Exception as exc:  # the chat must still open
                    log.warning("real feed failed (%s), using the stub", exc)
                break
    from .feed_stub import get_feed as stub
    return stub(business_id)


def find(business_id: str, suggestion_id: str) -> dict | None:
    for s in get_feed(business_id).get("suggestions", []):
        if s["id"] == suggestion_id or suggestion_id in (s.get("members") or []):
            return s
    return None
