"""/city: seed -> 813 Store entities, stores API, the notification -> SSE + event, the room hook. Fake brokers only."""
import asyncio
import json
import re
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from kaiku import store
from kaiku.app import app
from kaiku.broker.fallback import BrokerUnavailable, FallbackBroker
from kaiku.broker.models import SDM_CONTEXT
from kaiku.city import router as cr
from kaiku.city import seed as cs
from kaiku.map import osm, room

REAL = Path(__file__).resolve().parents[1] / "data" / "turku_businesses.json"
ITEMS = cs.load_businesses(REAL)


def test_seed_builds_813_store_entities_with_sdm_shape():
    ents = cs.build_entities(ITEMS)
    assert len(ents) == 813
    e = next(x for x in ents if x["id"] == "urn:ngsi-ld:Store:osm-n297492710")
    assert e["type"] == "Store" and e["name"]["value"] == "Hugo"
    assert e["location"] == {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [22.259131, 60.439035]}}
    assert e["holidayHoursStatus"]["value"] == {"date": "2026-12-24", "status": "missing", "seed": True}
    assert e["address"]["value"]["addressLocality"] == "Turku" and e["source"]["value"].startswith("OpenStreetMap")
    assert all(x["id"].startswith("urn:ngsi-ld:Store:osm-") for x in ents)
    assert sum(1 for x in ents if x["holidayHoursStatus"]["value"]["status"] == "known") == 2
    assert "—" not in json.dumps(ents, ensure_ascii=False)


def test_seed_batches_of_100_with_sdm_link_and_is_idempotent():
    posted, have = [], {}

    def handler(req: httpx.Request):
        if req.method == "GET":
            assert SDM_CONTEXT in req.headers["link"]
            return httpx.Response(200, json=[{"id": i, "holidayHoursStatus": {"value": v}} for i, v in have.items()])
        body = json.loads(req.content)
        assert len(body) <= 100 and SDM_CONTEXT in req.headers["link"]
        assert "entityOperations/upsert" in req.url.path
        posted.append((req.url.query.decode(), len(body)))
        for e in body:
            have[e["id"]] = e["holidayHoursStatus"]["value"]
        return httpx.Response(204)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    out = cs.seed(http=http, items=ITEMS)
    assert out["ok"] and out["created"] == 813 and sum(n for _, n in posted) == 813 and len(posted) == 9
    assert all(q == "options=update" for q, _ in posted)
    posted.clear()
    assert cs.seed(http=http, items=ITEMS)["created"] == 0 and not posted  # idempotent: nothing written
    have["urn:ngsi-ld:Store:osm-n297492710"] = {"date": "2026-12-24", "status": "approved", "via": "room"}
    out = cs.seed(force=True, http=http, items=ITEMS)
    assert out["reset"] == 1 and posted == [("", 1)]  # replace (no options) drops the room's holidayHours


def test_seed_never_raises_when_broker_down():
    def boom(req):
        raise httpx.ConnectError("down")
    out = cs.seed(http=httpx.Client(transport=httpx.MockTransport(boom)), items=ITEMS)
    assert out["ok"] is False and "ConnectError" in out["error"]


def _orion_rows(ents):
    """What Orion returns for GET /entities?attrs=... (normalized, keys compacted by the Link context)."""
    out = []
    for e in ents:
        e = {k: v for k, v in e.items() if k in ("id", "type", "name", "location", "category", "holidayHoursStatus")}
        out.append(e)
    out[0]["holidayHoursStatus"] = {"type": "Property", "value": {"date": "2026-12-24", "status": "approved", "via": "room"}}
    out[0]["holidayHours"] = {"type": "Property", "value": {"date": "2026-12-24", "hours": [{"start": "10:00", "end": "14:00"}]}}
    return out


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    shutil.copy(REAL, tmp_path / "turku_businesses.json")
    import importlib
    importlib.import_module("kaiku.map.router")._hits.clear()
    with TestClient(app) as c:
        yield c


def fake_orion(monkeypatch, ents):
    seen = []

    def handler(req):
        seen.append(req)
        if "/entities" in req.url.path and req.method == "GET":
            return httpx.Response(200, json=ents)
        return httpx.Response(404)
    monkeypatch.setattr(cr, "_async_client", lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return seen


def test_stores_api_reads_orion(client, monkeypatch):
    seen = fake_orion(monkeypatch, _orion_rows(cs.build_entities(ITEMS)))
    d = client.get("/api/city/stores").json()
    assert d["source"] == "orion-ld" and len(d["rows"]) == 813
    assert d["counts"] == {"total": 813, "missing": 810, "known": 2, "approved": 1}
    hugo = next(r for r in d["rows"] if r["s"] == "approved")
    assert set(hugo) >= {"id", "n", "c", "lon", "lat", "s", "a"} and hugo["a"] == "10-14"
    q = seen[0].url.params
    assert q["type"] == "Store" and q["idPattern"] == "^urn:ngsi-ld:Store:osm-" and "holidayHoursStatus" in q["attrs"]
    assert SDM_CONTEXT in seen[0].headers["link"]
    assert client.get("/api/city/stores?only=approved").json()["rows"][0]["n"] == hugo["n"]


def test_stores_api_fallback_when_broker_down(client, monkeypatch):
    def boom(req):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(cr, "_async_client", lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    d = client.get("/api/city/stores").json()
    assert d["source"] == "fallback" and d["counts"]["total"] == 813


def test_judge_gives_curl_and_one_entity(client, monkeypatch):
    fake_orion(monkeypatch, cs.build_entities(ITEMS)[:2])
    d = client.get("/api/city/judge").json()
    assert "type=Store&limit=2" in d["curl"] and SDM_CONTEXT in d["curl"] and d["broker_up"]
    assert d["entity"]["type"] == "Store"


NOTE = {"id": "urn:ngsi-ld:Notification:1", "type": "Notification", "subscriptionId": "urn:ngsi-ld:subscription:x",
        "data": [{"id": "urn:ngsi-ld:Store:osm-n297492710", "type": "Store",
                  "name": {"type": "Property", "value": "Hugo"},
                  "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [22.259131, 60.439035]}},
                  "holidayHoursStatus": {"type": "Property", "observedAt": "2026-11-07T18:00:00.000Z",
                                         "value": {"date": "2026-12-24", "status": "approved", "via": "room"}}},
                 {"id": "urn:ngsi-ld:Store:osm-n1", "type": "Store", "name": {"type": "Property", "value": "Seeded"},
                  "holidayHoursStatus": {"type": "Property", "value": {"date": "2026-12-24", "status": "missing", "seed": True}}}]}


def test_notify_pushes_store_sse_and_emits_broker_event(client):
    q = asyncio.Queue()
    cr._queues.add(q)
    cr._seen.clear()
    try:
        before = len(store.recent_events(500))
        r = client.post("/city/notify", json=NOTE)
        assert r.status_code == 204
        item = q.get_nowait()
        assert item["id"] == "osm-n297492710" and item["status"] == "approved" and item["lon"] == 22.259131
        assert q.empty()  # the seeded 'missing' Store is filtered out
        evs = [e for e in store.recent_events(500)[before:] if e.step == "broker"]
        assert len(evs) == 1 and evs[0].title_en == "Subscription fired: Hugo approved Christmas Eve hours"
        assert evs[0].detail["source"] == "city"
        client.post("/city/notify", json=NOTE)  # same (id, observedAt) within 5 s: deduped
        assert q.empty()
    finally:
        cr._queues.discard(q)


class Recorder(FallbackBroker):
    def __init__(self):
        super().__init__()
        self.writes = []

    def set_default(self, eid, attr, value, observed_at=None):
        self.writes.append(("default", eid, attr, value))
        return super().set_default(eid, attr, value, observed_at)

    def set_status(self, eid, attr, value, observed_at=None):
        self.writes.append(("status", eid, attr, value))
        return super().set_status(eid, attr, value, observed_at)


def test_room_answer_writes_approved_status_and_fires_subscription(client, monkeypatch):
    fb = Recorder()
    import kaiku.broker as kb
    monkeypatch.setattr(kb, "get_broker", lambda: fb)
    got = []
    fb.create_subscription(cr.SUB_NAME, ["holidayHoursStatus"], lambda n: got.append(n))
    client.get("/join")
    bid = room.load_state()["assignments"][client.cookies["kaiku_room"]]
    r = client.post("/api/room/answer", json={"business_id": bid, "answer": "10-14"})
    assert r.status_code == 200 and r.json()["ok"]
    eid = f"urn:ngsi-ld:Store:{bid}"
    assert ("default", eid, "holidayHours", {"date": "2026-12-24", "hours": [{"start": "10:00", "end": "14:00"}]}) in fb.writes
    assert ("status", eid, "holidayHoursStatus", {"date": "2026-12-24", "status": "approved", "via": "room"}) in fb.writes
    assert any(d["holidayHoursStatus"]["value"]["status"] == "approved" for n in got for d in n["data"])


def test_room_answer_still_ok_when_broker_raises(client, monkeypatch):
    class Dead:
        name = "orion-ld"

        def __getattr__(self, k):
            def f(*a, **kw):
                raise BrokerUnavailable("down")
            return f
    import kaiku.broker as kb
    monkeypatch.setattr(kb, "get_broker", lambda: Dead())
    client.get("/join")
    bid = room.load_state()["assignments"][client.cookies["kaiku_room"]]
    r = client.post("/api/room/answer", json={"business_id": bid, "answer": "closed"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["answer"] == "suljettu"


def test_parse_hours():
    assert cr.parse_hours(room.parse_answer("10-14")) == [{"start": "10:00", "end": "14:00"}]
    assert cr.parse_hours(room.parse_answer("9:30-13")) == [{"start": "09:30", "end": "13:00"}]
    assert cr.parse_hours(room.parse_answer("suljettu")) == "closed"
    assert cr.parse_hours(room.parse_answer("normaalisti")) == "regular"
    assert cr.hours_display([{"start": "09:30", "end": "13:00"}]) == "9:30-13"


def test_page_renders_with_hooks(client):
    r = client.get("/city?intro=0&room=1")
    assert r.status_code == 200
    for s in ("maplibre5/maplibre-gl.js", "city.js", "city.css", "FOR THE JUDGE", "OpenStreetMap", "Open-Meteo", "/api/room/qr.svg"):
        assert s in r.text, s
    assert "—" not in r.text
    assert 'href="/city"' in client.get("/fiware").text


def test_sub_name_is_per_test_server(monkeypatch):
    from kaiku.city import router as cr
    monkeypatch.setenv("PUBLIC_URL", "https://kaiku.hankintaviikko.fi")
    assert cr.sub_name() == cr.SUB_NAME
    monkeypatch.setenv("PUBLIC_URL", "http://127.0.0.1:8230")
    assert cr.sub_name() == cr.SUB_NAME + "-8230"


def test_vehicles_api_shape_unchanged_and_act_two_layers(client, monkeypatch):
    async def fake():
        return {"buses": [{"id": "bus-1", "lon": 22.27, "lat": 60.45, "heading": 90, "line": "1", "dest": "Satama", "delay": 0}],
                "ships": [{"id": "ship-1", "lon": 22.21, "lat": 60.437, "heading": 270, "name": "VIKING GRACE"}],
                "weather": {"temp": 4.2, "wtype": "cloudy"}, "source": "broker"}
    monkeypatch.setattr(cr, "_vehicles", fake)
    d = client.get("/api/city/vehicles").json()
    assert set(d) == {"buses", "ships", "weather", "counts", "source"}
    assert d["buses"][0][:4] == ["bus-1", 22.27, 60.45, 90] and len(d["buses"][0]) == 7
    assert d["ships"][0] == ["ship-1", 22.21, 60.437, 270, "VIKING GRACE"]
    assert 'id="ccover"' in client.get("/city").text
    js = (Path(__file__).resolve().parents[1] / "kaiku" / "web" / "static" / "city.js").read_text()
    for lid in ("city-beacon", "city-beacon-core", "city-glow"):
        assert re.search(r'addLayer\(\s*\{\s*id:\s*"' + lid + '"', js), lid
    for s in ('type: "heatmap"', "harbour", "areTilesLoaded", "maxTileCacheSize", "SHIPS (CACHE)"):
        assert s in js, s
