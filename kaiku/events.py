"""Event bus: emit() persists to SQLite and fans out to SSE subscribers."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from . import store
from .schema import Event

router = APIRouter()
_subs: set[asyncio.Queue] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None


def _fan(e: Event) -> None:
    for q in list(_subs):
        try:
            q.put_nowait(e)
        except asyncio.QueueFull:
            pass


def emit(e: Event) -> Event:
    """Persist and push. Safe from sync code, threads and the event loop."""
    e = store.save_event(e)
    try:
        asyncio.get_running_loop()
        _fan(e)
    except RuntimeError:
        if _loop is not None and _loop.is_running():
            _loop.call_soon_threadsafe(_fan, e)
    return e


def _sse(e: Event) -> str:
    return f"id: {e.id}\nevent: kaiku\ndata: {e.model_dump_json()}\n\n"


@router.get("/api/events")
async def stream(replay: int = Query(0), last: int = Query(50, ge=0, le=500)):
    global _loop
    _loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subs.add(q)
    backlog = store.recent_events(last) if replay else []
    seen = max([e.id or 0 for e in backlog], default=0)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            for e in backlog:
                yield _sse(e)
            if not backlog:
                yield ": connected\n\n"
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if (e.id or 0) > seen:
                    yield _sse(e)
        finally:
            _subs.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/events/recent")
def recent(limit: int = Query(50, ge=1, le=500), business: Optional[str] = None):
    evs = store.recent_events(limit)
    if business:
        evs = [e for e in evs if e.business_id == business]
    return [json.loads(e.model_dump_json()) for e in evs]
