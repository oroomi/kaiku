"""The decide step: issue a link, wait for the owner (future keyed by suggestion id), return a Decision."""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from .. import chain, store
from ..schema import Decision
from . import tokens

_waiting: dict[str, tuple[asyncio.AbstractEventLoop, "asyncio.Future"]] = {}


def pending() -> list[str]:
    return list(_waiting)


def resolve(suggestion_id: str, decision) -> bool:
    """Resolve the awaiting decide future. True the first time, False if nobody waits (or already resolved)."""
    w = _waiting.pop(suggestion_id, None)
    if w is None:
        return False
    loop, fut = w
    d = decision if isinstance(decision, dict) else decision.model_dump(mode="json")

    def _set():
        if not fut.done():
            fut.set_result(d)
    loop.call_soon_threadsafe(_set)
    return True


def _to_decision(sid: str, d: dict) -> Decision:
    return Decision(**{k: v for k, v in d.items() if k in Decision.model_fields} | {"suggestion_id": sid})


def _mark_expired(sid: str) -> None:
    """Record on the suggestion that the owner did not answer in time (late POSTs then get 410)."""
    try:
        s = store.get_suggestion(sid)
        if s and s.status in ("proposed", "sent"):
            s.status = "expired"
            store.save_suggestion(s)
    except Exception:
        pass


async def decide_step(suggestion) -> Decision:
    sid, bid = suggestion.id, suggestion.business_id
    link = tokens.link_for(sid, bid)
    s = store.get_suggestion(sid) or suggestion
    if not any(c.channel == "decide_link" for c in s.channel_log):
        from ..schema import ChannelLog
        from datetime import datetime, timezone
        s.channel_log.append(ChannelLog(channel="decide_link", at=datetime.now(timezone.utc).isoformat(), detail=link))
        store.save_suggestion(s)
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _waiting[sid] = (loop, fut)
    timeout = float(os.environ.get("KAIKU_DECIDE_TIMEOUT_S", "600"))
    try:
        d = await asyncio.wait_for(fut, timeout)
    except asyncio.TimeoutError:
        _waiting.pop(sid, None)
        _mark_expired(sid)
        # "timeout" is outside the Decision literal on purpose: no owner answer, nothing to apply
        return Decision.model_construct(suggestion_id=sid, action="timeout", edited=None, reason_chip=None,
                                        standing_permission=False, via="web", at="")
    finally:
        _waiting.pop(sid, None)
    return _to_decision(sid, d)


chain.register("decide", decide_step)
