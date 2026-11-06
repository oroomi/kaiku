"""FastMCP server: tools and resources over a Gateway. Errors are explicit JSON, flagged isError."""
from __future__ import annotations

import contextlib
import functools
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .broker import BrokerError
from .config import Config
from .core import GateError, Gateway


def _j(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)


def _guard(fn):
    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        try:
            r = fn(*a, **kw)
            if hasattr(r, "__await__"):
                r = await r
            return _j(r)
        except GateError as e:
            raise ToolError(_j({"error": "refused", "message": str(e)})) from e
        except BrokerError as e:
            raise ToolError(_j({"error": "broker", "status": e.status, "message": e.message})) from e
    return wrapper


READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
PROPOSE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DECIDE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


def build_server(gateway: Gateway | None = None, cfg: Config | None = None, *, name: str = "ngsi-ld",
                 streamable_path: str = "/mcp", open_hosts: bool = False) -> FastMCP:
    gw = gateway or Gateway(cfg)
    kw: dict[str, Any] = {"streamable_http_path": streamable_path}
    if open_hosts:
        kw["transport_security"] = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp = FastMCP(
        name,
        instructions=(
            "Tools for an NGSI-LD context broker. Reads are free. Writes go through a human gate: "
            "propose_update only writes a PROPOSED instance and never changes live data; a human approves "
            "with approve(). Never claim a change is live until approve() has returned status approved."
        ),
        **kw,
    )

    @mcp.tool(annotations=READ)
    @_guard
    async def list_entity_types() -> str:
        """List the entity types present in the broker."""
        return await gw.list_entity_types()

    @mcp.tool(annotations=READ)
    @_guard
    async def query_entities(type: str, q: str | None = None, georel: str | None = None, limit: int = 20,
                             geometry: str | None = None, coordinates: str | None = None,
                             attrs: str | None = None) -> str:
        """Query entities of a type. q is an NGSI-LD query (e.g. 'temperature>20'). georel (e.g. 'near;maxDistance==500')
        needs geometry ('Point') and coordinates ('[24.94,60.17]'). Returns the default instance of each attribute;
        use get_entity for every datasetId instance."""
        return await gw.query_entities(type, q, georel, limit, geometry, coordinates, attrs)

    @mcp.tool(annotations=READ)
    @_guard
    async def get_entity(id: str, include_all_instances: bool = True) -> str:
        """Get one entity. With include_all_instances every datasetId instance of an attribute is returned
        (default, proposed, per-source), each with its observedAt."""
        return await gw.get_entity(id, include_all_instances)

    @mcp.tool(annotations=READ)
    @_guard
    async def get_attribute_history(id: str, attr: str) -> str:
        """Time series of one attribute through the broker's temporal API. Says supported=false if the broker has none."""
        return await gw.get_attribute_history(id, attr)

    @mcp.tool(annotations=PROPOSE)
    @_guard
    async def propose_update(id: str, attr: str, value: Any, reason: str) -> str:
        """Propose a new value for an attribute. Writes a PROPOSED instance (datasetId urn:ngsi-ld:dataset:kaiku:proposed)
        and returns a proposal_id. It NEVER changes the live value. A human must approve it."""
        return await gw.propose_update(id, attr, value, reason)

    @mcp.tool(annotations=READ)
    @_guard
    async def list_proposals(status: str | None = "pending") -> str:
        """List proposals. status: pending (default), approved, rejected, superseded, or all."""
        return gw.list_proposals(status)

    if not gw.cfg.hide_decisions:
        @mcp.tool(annotations=DECIDE)
        @_guard
        async def approve(proposal_id: str, approver: str) -> str:
            """HUMAN DECISION. Writes the proposed value to the live (default) instance and records who approved.
            Call only when a human has said yes, and pass that human's name as approver."""
            return await gw.approve(proposal_id, approver)

        @mcp.tool(annotations=DECIDE)
        @_guard
        async def reject(proposal_id: str, reason: str) -> str:
            """HUMAN DECISION. Rejects a proposal; the live value stays untouched."""
            return await gw.reject(proposal_id, reason)

    @mcp.tool(annotations=PROPOSE)
    @_guard
    async def subscribe(type: str, q: str | None, notify_url: str, description: str = "") -> str:
        """Create a subscription: the broker POSTs matching entity changes to notify_url."""
        return await gw.subscribe(type, q, notify_url, description)

    @mcp.tool(annotations=READ)
    @_guard
    async def list_subscriptions() -> str:
        """List the broker's subscriptions."""
        return await gw.list_subscriptions()

    @mcp.tool(annotations=DECIDE)
    @_guard
    async def unsubscribe(id: str) -> str:
        """Delete a subscription by id."""
        return await gw.unsubscribe(id)

    @mcp.resource("ngsi-ld://types", mime_type="application/json")
    async def types_resource() -> str:
        return _j(await gw.list_entity_types())

    @mcp.resource("ngsi-ld://entity/{id}", mime_type="application/json")
    async def entity_resource(id: str) -> str:
        return _j(await gw.get_entity(id, True))

    mcp.gateway = gw  # type: ignore[attr-defined]
    return mcp


def mount(app, path: str = "/mcp", gateway: Gateway | None = None, cfg: Config | None = None) -> FastMCP:
    """Mount the MCP server (streamable HTTP) on a FastAPI/Starlette app at `path` (endpoint is `path`/)."""
    mcp = build_server(gateway, cfg, streamable_path="/", open_hosts=True)
    sub = mcp.streamable_http_app()
    app.mount(path, sub)
    prev = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(a):
        async with prev(a):
            async with mcp.session_manager.run():
                yield

    app.router.lifespan_context = lifespan
    return mcp
