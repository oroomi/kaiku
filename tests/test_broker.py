import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.broker import client as client_mod
from kaiku.broker.fallback import FallbackBroker, as_list, q_matches
from kaiku.broker.models import business_to_entity, furry_paw, hours_value, dataset_id
from kaiku.broker.router import handle_notification, holiday_label, router
from kaiku.broker.subs import ensure_subscriptions

EID = "urn:ngsi-ld:Store:furry-paw"
D = "2026-12-24"


def seeded(fb=None):
    fb = fb or FallbackBroker()
    fb.upsert_entity(business_to_entity(furry_paw(), status={"date": D, "status": "applied"}))
    return fb


def test_entity_shape():
    e = business_to_entity(furry_paw(), {"lastyear": (hours_value(D, "closed"), "2025-12-24T00:00:00.000Z"),
                                         "default": (hours_value(D, "closed"), None)})
    assert e["id"] == EID and e["type"] == "Store"
    assert e["location"]["type"] == "GeoProperty" and e["location"]["value"]["type"] == "Point"
    hh = e["holidayHours"]
    assert hh[0]["datasetId"] == "urn:ngsi-ld:dataset:kaiku:lastyear" and hh[0]["observedAt"]
    assert "datasetId" not in hh[1]
    assert "—" not in str(e)


def test_instances_per_datasetid_and_default():
    fb = seeded()
    for src in ("lastyear", "google", "proposed"):
        fb.append_instance(EID, "holidayHours", hours_value(D, "closed"), src)
    fb.set_default(EID, "holidayHours", hours_value(D, [{"start": "09:00", "end": "13:00"}]))
    inst = as_list(fb.get_entity(EID)["holidayHours"])
    assert len(inst) == 4
    assert {i.get("datasetId") for i in inst} == {dataset_id(s) for s in ("lastyear", "google", "proposed")} | {None}
    fb.append_instance(EID, "holidayHours", hours_value(D, "closed"), "google")  # replaces, not duplicates
    assert len(as_list(fb.get_entity(EID)["holidayHours"])) == 4


def test_single_instance_is_object_like_orion():
    fb = seeded()
    assert isinstance(fb.get_entity(EID)["holidayHoursStatus"], dict)


def test_subscription_idempotent_and_fires_via_callback():
    fb = seeded()
    got = []
    a = ensure_subscriptions(fb, got.append)
    assert ensure_subscriptions(fb, got.append) == a and len(fb.list_subscriptions()) == 2
    fb.set_default(EID, "holidayHoursStatus", {"date": D, "status": "approved"})  # q false: (a) silent
    assert got == []
    fb.set_default(EID, "holidayHoursStatus", {"date": D, "status": "missing"})
    assert len(got) == 1 and got[0]["type"] == "Notification"
    fired = handle_notification(got[0])
    assert fired[0]["kind"] == "missing"
    fb.set_default(EID, "holidayHours", hours_value(D, "closed"))
    assert any(f["kind"] == "resolved" for n in got[1:] for f in handle_notification(n))


def test_router_ignores_source_instances_and_dedupes():
    note = {"subscriptionId": "s", "data": [{"id": EID, "type": "Store", "holidayHours": [
        {"type": "Property", "value": hours_value(D, "closed"), "datasetId": dataset_id("google")}]}]}
    assert handle_notification(note) == []
    ok = {"subscriptionId": "s", "data": [{"id": EID, "type": "Store", "holidayHours": [
        {"type": "Property", "value": hours_value("2026-12-25", "closed"), "observedAt": "2026-11-06T10:00:00.000Z"}]}]}
    assert len(handle_notification(ok)) == 1
    assert handle_notification(ok) == []


def test_q_matching():
    attrs = {"s": {"type": "Property", "value": {"status": "missing"}}}
    assert q_matches('s.status=="missing"', attrs) and q_matches('s[status]=="missing"', attrs)
    assert not q_matches('s.status=="approved"', attrs) and q_matches(None, attrs)


def test_holiday_labels():
    assert holiday_label("2026-12-24") == ("jouluaaton", "Christmas Eve")
    assert holiday_label("2026-05-01")[1] == "1.5."


def test_notify_endpoint():
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    note = {"subscriptionId": "s", "data": [{"id": EID, "type": "Store",
            "holidayHoursStatus": {"type": "Property", "value": {"date": "2027-12-24", "status": "missing"},
                                   "observedAt": "2026-11-06T11:00:00.000Z"}}]}
    r = c.post("/broker/notify", json=note)
    assert r.status_code == 200 and r.json()["fired"][0]["kind"] == "missing"


def test_get_broker_falls_back_when_dead(monkeypatch):
    monkeypatch.setenv("KAIKU_BROKER_URL", "http://127.0.0.1:1")
    from kaiku.broker import get_broker, reset_broker
    reset_broker()
    b = get_broker()
    assert b.status() == "fallback"
    b.upsert_entity(business_to_entity(furry_paw()))
    assert b.get_entity(EID)["name"]["value"].startswith("Furry Paw")
    reset_broker()


def _orion_up():
    try:
        return client_mod.OrionClient().alive()
    except Exception:
        return False


@pytest.mark.skipif(not _orion_up(), reason="Orion-LD not running")
def test_live_orion_multi_instance():
    c = client_mod.OrionClient()
    eid = "urn:ngsi-ld:Store:pytest-live"
    c.delete_entity(eid)
    e = business_to_entity(furry_paw(), status={"date": D, "status": "applied"})
    e["id"] = eid
    c.upsert_entity(e)
    c.append_instance(eid, "holidayHours", hours_value(D, "closed"), "lastyear")
    c.append_instance(eid, "holidayHours", hours_value(D, "closed"), "google")
    c.set_default(eid, "holidayHours", hours_value(D, "closed"))
    got = client_mod.instances(c.get_entity(eid), "holidayHours")
    assert set(got) == {"lastyear", "google", "default"}
    c.delete_entity(eid)
