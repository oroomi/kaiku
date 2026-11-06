"""Feed client. Uses kaiku.suggest.feed (the real engine) when it imports, kaiku.chat.feed_stub otherwise."""
from __future__ import annotations

import logging

log = logging.getLogger("kaiku.chat.feed")


def get_feed(business_id: str) -> dict:
    try:
        from ..suggest import feed as real  # type: ignore
    except Exception:
        real = None
    if real is not None:
        for name in ("get_feed", "build_feed", "feed_for"):
            fn = getattr(real, name, None)
            if callable(fn):
                try:
                    r = fn(business_id)
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
