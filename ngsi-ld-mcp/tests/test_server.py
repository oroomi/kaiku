"""The MCP layer: tool list, JSON results, isError on refusals, resources, FastAPI mount."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from conftest import ID
from ngsi_ld_mcp import Config, Gateway, build_server
from ngsi_ld_mcp.broker import Broker

TOOLS = {"list_entity_types", "query_entities", "get_entity", "get_attribute_history", "propose_update",
         "list_proposals", "approve", "reject", "subscribe", "list_subscriptions", "unsubscribe"}


async def call(c, name, **args):
    r = await c.call_tool(name, args)
    t = r.content[0].text
    # FastMCP prefixes tool errors with 'Error executing tool X: '; the payload after it is JSON
    return r.isError, json.loads(t[t.index("{"):])


async def test_tool_list_and_flow(gw):
    server = build_server(gw)
    async with connect(server._mcp_server) as c:
        assert {t.name for t in (await c.list_tools()).tools} == TOOLS
        err, d = await call(c, "list_entity_types")
        assert not err and d["types"] == ["Test"]
        err, d = await call(c, "query_entities", type="Test")
        assert d["count"] == 1
        err, d = await call(c, "get_entity", id=ID)
        assert d["id"] == ID
        err, d = await call(c, "get_attribute_history", id=ID, attr="hours")
        assert d["supported"] is False
        err, p = await call(c, "propose_update", id=ID, attr="hours", value="9-13", reason="r")
        assert not err
        err, d = await call(c, "list_proposals")
        assert d["count"] == 1
        err, d = await call(c, "approve", proposal_id=p["proposal_id"], approver="Dayo")
        assert d["status"] == "approved"
        err, d = await call(c, "subscribe", type="Test", q=None, notify_url="http://x.y/z", description="d")
        assert d["created"]
        err, d = await call(c, "list_subscriptions")
        assert d["count"] == 1
        err, d = await call(c, "unsubscribe", id=d["subscriptions"][0]["id"])
        assert "deleted" in d
        err, p2 = await call(c, "propose_update", id=ID, attr="hours", value="closed", reason="r")
        err, d = await call(c, "reject", proposal_id=p2["proposal_id"], reason="no")
        assert d["status"] == "rejected"


async def test_errors_are_explicit(gw):
    server = build_server(gw)
    async with connect(server._mcp_server) as c:
        err, d = await call(c, "approve", proposal_id="prop-x", approver="Dayo")
        assert err and d["error"] == "refused"
        err, d = await call(c, "get_entity", id="urn:ngsi-ld:Test:nope")
        assert err and d["error"] == "broker" and d["status"] == 404


async def test_resources(gw):
    server = build_server(gw)
    async with connect(server._mcp_server) as c:
        r = await c.read_resource("ngsi-ld://types")
        assert json.loads(r.contents[0].text)["types"] == ["Test"]
        r = await c.read_resource(f"ngsi-ld://entity/{ID}")
        assert json.loads(r.contents[0].text)["id"] == ID


async def test_hide_decisions(fb, tmp_path):
    cfg = Config(url="http://fake", proposals_path=str(tmp_path / "p.json"), hide_decisions=True)
    server = build_server(Gateway(cfg, Broker(cfg, transport=fb.transport)))
    async with connect(server._mcp_server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert "approve" not in names and "reject" not in names and "propose_update" in names


def test_mount_on_fastapi(gw):
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    from ngsi_ld_mcp import mount

    app = FastAPI()
    mount(app, "/mcp", gateway=gw)
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    with TestClient(app) as tc:
        r = tc.post("/mcp/", json=init, headers=hdr)
        assert r.status_code == 200 and "ngsi-ld" in r.text
