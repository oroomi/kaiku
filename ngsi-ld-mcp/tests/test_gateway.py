import json

import pytest

from conftest import ID
from ngsi_ld_mcp import Config, Gateway, GateError
from ngsi_ld_mcp.broker import Broker, BrokerError

PROPOSED = "urn:ngsi-ld:dataset:kaiku:proposed"


def default_value(fb, attr="hours"):
    return [i for i in fb.inst(fb.entities[ID], attr) if not i.get("datasetId")][0]["value"]


async def test_list_entity_types(gw):
    assert (await gw.list_entity_types()) == {"types": ["Test"]}


async def test_query_entities(gw):
    r = await gw.query_entities("Test")
    assert r["count"] == 1 and r["entities"][0]["id"] == ID
    assert (await gw.query_entities("Test", q="hours==9-17"))["count"] == 1
    assert (await gw.query_entities("Test", q="hours==nope"))["count"] == 0
    assert (await gw.query_entities("Nothing"))["count"] == 0


async def test_query_limit_clamped(gw):
    assert (await gw.query_entities("Test", limit=9999))["limit"] == 200


async def test_georel_needs_geometry(gw):
    with pytest.raises(GateError, match="geometry"):
        await gw.query_entities("Test", georel="near;maxDistance==100")


async def test_get_entity_all_instances(gw):
    e = await gw.get_entity(ID)
    assert e["hours"]["value"] == "9-17" and e["hours"]["observedAt"]
    ds = {i["datasetId"] for i in e["temperature"]}
    assert ds == {"default", "urn:ngsi-ld:dataset:src:b"}
    one = await gw.get_entity(ID, include_all_instances=False)
    assert one["temperature"]["datasetId"] == "default"


async def test_get_entity_missing_is_explicit(gw):
    with pytest.raises(BrokerError) as ei:
        await gw.get_entity("urn:ngsi-ld:Test:nope")
    assert ei.value.status == 404


async def test_history_unsupported(gw):
    r = await gw.get_attribute_history(ID, "hours")
    assert r["supported"] is False and "temporal" in r["reason"]


async def test_history_supported(fb, tmp_path):
    fb.temporal = True
    cfg = Config(url="http://fake", proposals_path=str(tmp_path / "p.json"))
    g = Gateway(cfg, Broker(cfg, transport=fb.transport))
    assert (await g.get_attribute_history(ID, "hours"))["supported"] is True


async def test_propose_never_touches_default(gw, fb):
    r = await gw.propose_update(ID, "hours", "9-13", "jouluaatto")
    assert r["status"] == "pending" and r["proposal_id"].startswith("prop-")
    assert default_value(fb) == "9-17"
    proposed = [i for i in fb.inst(fb.entities[ID], "hours") if i.get("datasetId") == PROPOSED]
    assert len(proposed) == 1 and proposed[0]["value"] == "9-13"
    assert proposed[0]["reason"]["value"] == "jouluaatto" and proposed[0]["observedAt"]
    e = await gw.get_entity(ID)
    assert e["pending_proposals"] == [r["proposal_id"]]


async def test_other_instances_survive_propose(gw, fb):
    await gw.propose_update(ID, "temperature", 9, "why")
    ds = {i.get("datasetId") for i in fb.inst(fb.entities[ID], "temperature")}
    assert ds == {None, "urn:ngsi-ld:dataset:src:b", PROPOSED}


async def test_propose_needs_reason_and_entity(gw):
    with pytest.raises(GateError):
        await gw.propose_update(ID, "hours", "x", "  ")
    with pytest.raises(BrokerError):
        await gw.propose_update("urn:ngsi-ld:Test:nope", "hours", "x", "r")


async def test_list_proposals(gw):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    assert gw.list_proposals()["proposals"][0]["proposal_id"] == p["proposal_id"]
    assert gw.list_proposals("approved")["count"] == 0
    assert gw.list_proposals("all")["count"] == 1


async def test_approve_writes_default_and_records_approver(gw, fb):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    out = await gw.approve(p["proposal_id"], "Dayo")
    assert out["status"] == "approved" and out["warnings"] == []
    assert default_value(fb) == "9-13"
    dflt = [i for i in fb.inst(fb.entities[ID], "hours") if not i.get("datasetId")][0]
    assert dflt["approvedBy"]["value"] == "Dayo" and dflt["proposalId"]["value"] == p["proposal_id"]
    prop = [i for i in fb.inst(fb.entities[ID], "hours") if i.get("datasetId") == PROPOSED][0]
    assert prop["proposalStatus"]["value"] == "approved" and prop["decidedBy"]["value"] == "Dayo"
    assert gw.store.get(p["proposal_id"])["approver"] == "Dayo"


async def test_approve_twice_and_unknown(gw):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    await gw.approve(p["proposal_id"], "Dayo")
    with pytest.raises(GateError, match="already approved"):
        await gw.approve(p["proposal_id"], "Dayo")
    with pytest.raises(GateError, match="unknown"):
        await gw.approve("prop-nope", "Dayo")


async def test_approve_needs_named_human(gw, fb):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    with pytest.raises(GateError, match="approver"):
        await gw.approve(p["proposal_id"], "")
    assert default_value(fb) == "9-17"


async def test_reject_leaves_default(gw, fb):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    out = await gw.reject(p["proposal_id"], "wrong day")
    assert out["status"] == "rejected" and default_value(fb) == "9-17"
    prop = [i for i in fb.inst(fb.entities[ID], "hours") if i.get("datasetId") == PROPOSED][0]
    assert prop["proposalStatus"]["value"] == "rejected"
    with pytest.raises(GateError):
        await gw.approve(p["proposal_id"], "Dayo")


async def test_new_proposal_supersedes_old(gw):
    a = await gw.propose_update(ID, "hours", "9-13", "r")
    b = await gw.propose_update(ID, "hours", "closed", "r2")
    assert gw.store.get(a["proposal_id"])["status"] == "superseded"
    with pytest.raises(GateError):
        await gw.approve(a["proposal_id"], "Dayo")
    await gw.approve(b["proposal_id"], "Dayo")


async def test_stale_default_warns(gw, fb):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    fb.entities[ID]["hours"] = [{"type": "Property", "value": "8-16"}, *[i for i in fb.inst(fb.entities[ID], "hours") if i.get("datasetId")]]
    out = await gw.approve(p["proposal_id"], "Dayo")
    assert out["warnings"] and "changed since" in out["warnings"][0]


async def test_proposals_survive_restart(gw, fb, tmp_path):
    p = await gw.propose_update(ID, "hours", "9-13", "r")
    cfg = Config(url="http://fake", proposals_path=gw.cfg.proposals_path)
    g2 = Gateway(cfg, Broker(cfg, transport=fb.transport))
    assert g2.list_proposals()["proposals"][0]["proposal_id"] == p["proposal_id"]
    await g2.approve(p["proposal_id"], "Dayo")
    assert default_value(fb) == "9-13"


async def test_recreate_fallback_off(fb, tmp_path):
    if fb.native:
        pytest.skip("native broker")
    cfg = Config(url="http://fake", proposals_path=str(tmp_path / "p.json"), recreate_fallback=False)
    g = Gateway(cfg, Broker(cfg, transport=fb.transport))
    with pytest.raises(GateError, match="RECREATE"):
        await g.propose_update(ID, "hours", "9-13", "r")
    assert default_value(fb) == "9-17"


async def test_subscriptions(gw):
    r = await gw.subscribe("Test", "hours==9-17", "http://example.org/hook", "watch")
    sid = r["subscription"]["id"]
    ls = await gw.list_subscriptions()
    assert ls["count"] == 1 and ls["subscriptions"][0]["uri"] == "http://example.org/hook"
    assert (await gw.unsubscribe(sid)) == {"deleted": sid}
    assert (await gw.list_subscriptions())["count"] == 0
    with pytest.raises(BrokerError):
        await gw.unsubscribe(sid)
    with pytest.raises(GateError):
        await gw.subscribe("Test", None, "ftp://x", "")


async def test_broker_down_is_explicit(tmp_path):
    cfg = Config(url="http://127.0.0.1:9", proposals_path=str(tmp_path / "p.json"))
    g = Gateway(cfg)
    with pytest.raises(BrokerError, match="unreachable"):
        await g.list_entity_types()
