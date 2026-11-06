"""Mounts the ngsi-ld-mcp streamable HTTP server at /mcp. Guarded: the app runs without the package.

The public mount hides approve/reject (NGSI_LD_MCP_HIDE_DECISIONS=1): an external agent can propose, never decide.
A fresh MCP server is built on every app start-up (the SDK's session manager can only run once per instance), and a
thin proxy mounted at /mcp forwards to the current one.
"""
from __future__ import annotations

import contextlib
import logging
import os

from fastapi import APIRouter

log = logging.getLogger("kaiku.mcp_bridge")
router = APIRouter()  # no routes of its own; the MCP app is mounted by install()
_current = {"app": None}


class _Proxy:
    def __init__(self, path: str):
        self.path = path

    async def __call__(self, scope, receive, send):
        app = _current["app"]
        if app is None:
            if scope["type"] == "http":
                await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"mcp not running"})
            return
        await app(scope, receive, send)


class _Slash:  # /mcp and /mcp/ both work (no 307 with an http:// Location behind the tunnel)
    def __init__(self, inner, path):
        self.inner, self.path = inner, path

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == self.path:
            scope = dict(scope, path=self.path + "/", raw_path=(self.path + "/").encode())
        await self.inner(scope, receive, send)


def install(app, path: str = "/mcp") -> bool:
    os.environ["NGSI_LD_MCP_HIDE_DECISIONS"] = "1"
    try:
        import ngsi_ld_mcp.server  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        log.warning("ngsi-ld-mcp not mounted: %s", exc)
        return False
    app.mount(path, _Proxy(path))
    app.add_middleware(_Slash, path=path)
    return True


@contextlib.asynccontextmanager
async def running():
    """Start a fresh MCP server for the life of the app; a no-op if the package is missing."""
    try:
        from ngsi_ld_mcp.config import Config
        from ngsi_ld_mcp.server import build_server

        from ..broker.models import SDM_CONTEXT
        from ..config import settings
        mcp = build_server(None, Config(url=settings.BROKER_URL, hide_decisions=True, context=SDM_CONTEXT),
                           streamable_path="/", open_hosts=True)
        sub = mcp.streamable_http_app()
    except Exception as exc:  # noqa: BLE001
        log.warning("ngsi-ld-mcp not started: %s", exc)
        yield
        return
    try:
        async with mcp.session_manager.run():
            _current["app"] = sub
            log.info("ngsi-ld-mcp running at /mcp")
            try:
                yield
            finally:
                _current["app"] = None
    except Exception as exc:  # noqa: BLE001
        log.warning("ngsi-ld-mcp stopped: %s", exc)
        _current["app"] = None
        yield
