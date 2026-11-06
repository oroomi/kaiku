"""Event bus: emit() persists to SQLite and fans out to SSE subscribers."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Query, Request
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


KEY_COOKIE = "kaiku_key"


def has_key(request: Request) -> bool:
    """True when the viewer holds the demo key (httponly cookie set by the keyed home page, or X-Kaiku-Key header)."""
    want = os.environ.get("KAIKU_ROOM_KEY", "")
    got = request.cookies.get(KEY_COOKIE, "") or request.headers.get("x-kaiku-key", "")
    return bool(want) and hmac.compare_digest(got.encode(), want.encode())


def _urls(o: Any, out: set) -> None:
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "decide_url" and isinstance(v, str) and v:
                out.add(v)
            _urls(v, out)
    elif isinstance(o, list):
        for v in o:
            _urls(v, out)


def _strip(o: Any, urls: set) -> Any:
    if isinstance(o, dict):
        return {k: _strip(v, urls) for k, v in o.items() if k != "decide_url"}
    if isinstance(o, list):
        return [_strip(v, urls) for v in o]
    if isinstance(o, str) and any(u in o for u in urls):
        return "\n".join(ln for ln in o.split("\n") if not any(u in ln for u in urls)).strip()
    return o


def public_view(d: dict, request: Request) -> dict:
    """The owner's decision link is a bearer secret: only a viewer with the demo key gets it (also out of message text)."""
    if has_key(request):
        return d
    urls: set = set()
    _urls(d, urls)
    return _strip(d, urls)


def _sse(e: Event, request: Optional[Request] = None) -> str:
    data = e.model_dump_json() if request is None or has_key(request) else json.dumps(public_view(json.loads(e.model_dump_json()), request), ensure_ascii=False, separators=(",", ":"))
    return f"id: {e.id}\nevent: kaiku\ndata: {data}\n\n"


@router.get("/api/events")
async def stream(request: Request, replay: int = Query(0), last: int = Query(50, ge=0, le=500)):
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
                yield _sse(e, request)
            if not backlog:
                yield ": connected\n\n"
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if (e.id or 0) > seen:
                    yield _sse(e, request)
        finally:
            _subs.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/events/recent")
def recent(request: Request, limit: int = Query(50, ge=1, le=500), business: Optional[str] = None):
    evs = store.recent_events(limit)
    if business:
        evs = [e for e in evs if e.business_id == business]
    return [public_view(json.loads(e.model_dump_json()), request) for e in evs]
