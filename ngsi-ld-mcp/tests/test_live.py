"""Live tests against a real Orion-LD on 127.0.0.1:1026. Skipped when the broker is down."""
import os

import httpx
import pytest

from ngsi_ld_mcp import Config, Gateway

URL = os.environ.get("NGSI_LD_URL", "http://127.0.0.1:1026")
ID = "urn:ngsi-ld:Test:mcp-1"
CTX = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"


def up() -> bool:
    try:
        return httpx.get(URL + "/version", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not up(), reason="no NGSI-LD broker on " + URL)


@pytest.fixture
async def live(tmp_path):
    cfg = Config(url=URL, proposals_path=str(tmp_path / "p.json"))
    g = Gateway(cfg)
    b = f"{URL}/ngsi-ld/v1/entities"
    httpx.delete(f"{b}/{ID}")
    r = httpx.post(b, headers={"Content-Type": "application/ld+json"}, json={
        "id": ID, "type": "Test", "@context": CTX,
        "hours": {"type": "Property", "value": "9-17", "observedAt": "2026-11-06T10:00:00Z"}})
    assert r.status_code == 201, r.text
    yield g
    httpx.delete(f"{b}/{ID}")
    await g.broker.close()


async def test_live_propose_approve_cycle(live):
    g = live
    assert "Test" in (await g.list_entity_types())["types"]
    assert (await g.query_entities("Test"))["count"] >= 1
    p = await g.propose_update(ID, "hours", "9-13", "live test")
    e = await g.get_entity(ID)
    insts = {i["datasetId"]: i for i in e["hours"]}
    assert insts["default"]["value"] == "9-17"  # default untouched by a proposal
    assert insts[g.cfg.proposed_dataset]["value"] == "9-13"
    out = await g.approve(p["proposal_id"], "live-test")
    assert out["status"] == "approved", out
    e = await g.get_entity(ID)
    insts = {i["datasetId"]: i for i in e["hours"]}
    assert insts["default"]["value"] == "9-13"
    assert insts["default"]["meta"]["approvedBy"] == "live-test"
    assert insts[g.cfg.proposed_dataset]["meta"]["proposalStatus"] == "approved"
    h = await g.get_attribute_history(ID, "hours")
    assert "supported" in h


async def test_live_reject(live):
    g = live
    p = await g.propose_update(ID, "hours", "closed", "live reject")
    await g.reject(p["proposal_id"], "no")
    e = await g.get_entity(ID)
    assert {i["datasetId"]: i for i in e["hours"]}["default"]["value"] == "9-17"


async def test_live_subscription(live):
    g = live
    r = await g.subscribe("Test", None, "http://127.0.0.1:9/hook", "mcp live test")
    sid = r["subscription"]["id"]
    try:
        assert any(s["id"] == sid for s in (await g.list_subscriptions())["subscriptions"])
    finally:
        await g.unsubscribe(sid)
