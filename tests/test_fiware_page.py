"""/fiware: the page, the read-only proxy, the broker-offline honesty. A fake broker stands in for Orion-LD."""
import httpx
import pytest
from fastapi.testclient import TestClient

from kaiku.app import app
from kaiku.fiware import router as fw

if not any(getattr(r, "path", "") == "/fiware" for r in app.routes):  # until app.py lists the module
    app.include_router(fw.router)
client = TestClient(app)

EID = "urn:ngsi-ld:Store:furry-paw"


def inst(hours, ds=None, date="2026-12-24", obs="2026-11-07T02:00:00.000Z"):
    i = {"type": "Property", "value": {"date": date, "hours": hours}, "observedAt": obs}
    if ds:
        i["datasetId"] = "urn:ngsi-ld:dataset:kaiku:" + ds
    return i


ENTITY = {"id": EID, "type": "Store", "name": {"type": "Property", "value": "Furry Paw"},
          "secret": "x", "holidayHours": [inst([{"start": "09:00", "end": "13:00"}]),
                                          inst([{"start": "09:00", "end": "13:00"}], "proposed"),
                                          inst("unknown", "google"), inst("closed", "lastyear", "2025-12-24")]}
SUBS = [{"id": "urn:ngsi-ld:subscription:1", "type": "Subscription", "subscriptionName": "kaiku-holiday-hours-missing",
         "watchedAttributes": ["holidayHoursStatus"], "status": "active", "isActive": True,
         "notification": {"endpoint": {"uri": "https://x.example/broker/notify"}, "timesSent": 3, "lastErrorReason": "secret-ish"},
         "jsonldContext": "https://ctx"}]


@pytest.fixture
def fake_broker(monkeypatch):
    calls = []

    async def get(path, params=None):
        calls.append((path, params))
        if path == f"/entities/{EID}":
            return 200, ENTITY
        if path == "/subscriptions":
            return 200, SUBS
        return 404, None
    monkeypatch.setattr(fw, "_orion_get", get)
    return calls


@pytest.fixture
def dead_broker(monkeypatch):
    async def get(path, params=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(fw, "_orion_get", get)
    monkeypatch.setattr(fw, "_fallback_entity", lambda eid: None)


def test_page_has_all_sections():
    r = client.get("/fiware")
    assert r.status_code == 200
    for s in ("ONE BUSINESS, FIVE DATASETIDS, ONE TRUTH", "THE CHAIN IN THE BROKER", "AN AI AGENT OVER NGSI-LD, WITH A HUMAN GATE",
              "SAME BROKER, CITY DATA", "JUDGE'S CURL AND THE MODEL", "HOW THIS MAPS TO THE AWARD", "/aura", "attrs=holidayHours",
              "openingHoursSpecification", "WHAT DID NOT WORK", "fiware.js"):
        assert s in r.text, s
    assert "—" not in r.text  # no em dashes


def test_entity_proxy_reads_and_marks_default(fake_broker):
    d = client.get("/api/fiware/entity", params={"id": EID, "attrs": "holidayHours,name"}).json()
    assert d["source"] == "orion-ld" and not d["broker_offline"]
    assert "secret" not in d["entity"]
    rows = d["instances"]
    assert [r["source"] for r in rows][0] == "default" and rows[0]["is_default"] is True
    assert {r["source"] for r in rows} == {"default", "proposed", "google", "lastyear"}
    assert next(r for r in rows if r["source"] == "google")["hours"].startswith("unknown")
    assert next(r for r in rows if r["source"] == "lastyear")["hours"] == "closed"
    assert fake_broker[0][1] == {"attrs": "holidayHours,name"}


@pytest.mark.parametrize("bad", ["urn:other:thing", "http://evil/x", "../etc", "urn:ngsi-ld:../x", "urn:ngsi-ld:a b", ""])
def test_entity_proxy_rejects_foreign_ids(fake_broker, bad):
    assert client.get("/api/fiware/entity", params={"id": bad}).status_code == 400
    assert fake_broker == []


def test_entity_proxy_limits_attrs(fake_broker):
    assert client.get("/api/fiware/entity", params={"id": EID, "attrs": "holidayHours,password"}).status_code == 400


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("path", ["/api/fiware/entity", "/api/fiware/subscriptions", "/api/fiware/mcp", "/api/fiware/events"])
def test_only_get(fake_broker, method, path):
    r = getattr(client, method)(path + ("?id=" + EID if path.endswith("entity") else ""))
    assert r.status_code == 405
    assert fake_broker == []


def test_broker_offline_is_honest(dead_broker):
    d = client.get("/api/fiware/entity", params={"id": EID}).json()
    assert d["broker_offline"] is True and d["source"] == "fallback"
    assert d["message"] == "broker offline, fallback store in use"
    assert d["entity"] is None and d["instances"] == []  # nothing invented
    s = client.get("/api/fiware/subscriptions").json()
    assert s["broker_offline"] and s["items"] == [] and "broker offline" in s["message"]


def test_missing_entity_is_not_invented(monkeypatch):
    async def get(path, params=None):
        return 404, None
    monkeypatch.setattr(fw, "_orion_get", get)
    d = client.get("/api/fiware/entity", params={"id": "urn:ngsi-ld:Store:nobody"}).json()
    assert d["entity"] is None and d["instances"] == []


def test_subscriptions_are_trimmed(fake_broker):
    d = client.get("/api/fiware/subscriptions").json()
    assert d["items"] == [{"name": "kaiku-holiday-hours-missing", "watched": ["holidayHoursStatus"],
                           "endpoint": "https://x.example/broker/notify", "status": "active"}]
    assert "read_at" in d


def test_broker_events_only_broker_step(tmp_path):
    from kaiku import events
    from kaiku.schema import Event
    events.emit(Event(step="detect", title_fi="a", title_en="Detect line"))
    events.emit(Event(step="broker", title_fi="b", title_en="Proposal written to the broker (24.12., datasetId proposed)"))
    items = client.get("/api/fiware/events").json()["items"]
    assert items and all(e["step"] == "broker" for e in items)
    assert any("Proposal written" in e["title_en"] for e in items)


def test_mcp_tool_list_and_example(monkeypatch):
    pytest.importorskip("ngsi_ld_mcp")
    from ngsi_ld_mcp.core import Gateway

    async def q(self, **kw):
        return {"count": 1, "entities": [{"id": EID, "type": "Store"}]}
    monkeypatch.setattr(Gateway, "query_entities", q)
    d = client.get("/api/fiware/mcp").json()
    names = {t["name"] for t in d["tools"]}
    assert {"query_entities", "propose_update", "get_entity"} <= names
    assert "approve" not in names  # hidden on the public endpoint: an agent proposes, a human decides
    assert d["call"]["tool"] == "query_entities" and d["example"]["count"] == 1
