import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("KAIKU_DB", str(Path(tempfile.mkdtemp()) / "t.sqlite"))
os.environ["KAIKU_STEP_GAP"] = "0"
TMP = Path(tempfile.mkdtemp())
os.environ["KAIKU_DATA_DIR"] = str(TMP)

from fastapi.testclient import TestClient  # noqa: E402

from kaiku import store  # noqa: E402
from kaiku.app import app  # noqa: E402
from kaiku.map import osm, room  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "overpass_sample.json"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("KAIKU_ROOM_KEY", "sekret")
    import importlib
    _r = importlib.import_module("kaiku.map.router")
    _r._hits.clear()
    monkeypatch.setenv("KAIKU_DATA_DIR", str(TMP))
    items = osm.parse(json.loads(FIX.read_text()))
    doc = {"source": osm.SOURCE, "mirror": "fixture", "label": "real", "fallback": False, "fetched_at": "x",
           "count": len(items), "businesses": items}
    (TMP / "turku_businesses.json").write_text(json.dumps(doc))
    (TMP / "room_state.json").unlink(missing_ok=True)
    with TestClient(app) as c:
        yield c


def test_parse_fixture():
    items = osm.parse(json.loads(FIX.read_text()))
    assert len(items) == 25  # 24 real + Testikahvila, the nameless node is dropped
    assert all(b["name"] and b["label"] == "real" and b["id"].startswith("osm-") for b in items)
    t = next(b for b in items if b["name"] == "Testikahvila")
    assert t["holiday_hours_found"] is True
    assert sum(1 for b in items if b["holiday_hours_found"]) == 1


def test_fallback_labelled():
    fb = osm.fallback_set()
    assert len(fb) == 40 and all(b["label"] == "fictional placeholder" for b in fb)


def test_build_cache_falls_back_offline(tmp_path):
    doc = osm.build_cache(tmp_path / "c.json", mirrors=["http://127.0.0.1:9/x"], retries=1, timeout=1, sleep=lambda s: None)
    assert doc["fallback"] is True and doc["label"] == "fictional placeholder" and doc["count"] == 40


def test_join_sets_cookie_and_round_robin(client):
    r1 = client.get("/join")
    assert r1.status_code == 200 and "kaiku_room" in r1.cookies and "You are now:" in r1.text
    c2 = TestClient(app)
    r2 = c2.get("/join")
    n1 = room.assign(r1.cookies["kaiku_room"])["name"]
    n2 = room.assign(r2.cookies["kaiku_room"])["name"]
    assert n1 != n2
    # sticky: same cookie, same business
    assert client.get("/join").text.count(n1.replace("&", "&amp;")) >= 1
    assert room.assign(r1.cookies["kaiku_room"])["name"] == n1


def test_known_holiday_business_never_assigned(client):
    names = {room.assign(f"t{i}")["name"] for i in range(24)}
    assert "Testikahvila" not in names


def test_answer_emits_events_and_updates_state(client):
    client.get("/join")
    bid = room.assign(client.cookies["kaiku_room"])["id"]
    before = len(store.recent_events(500))
    r = client.post("/api/room/answer", json={"business_id": bid, "answer": "9-13"})
    assert r.status_code == 200 and r.json()["answer"] == "9-13"
    evs = store.recent_events(500)[before:]
    assert [e.step for e in evs] == ["decide", "apply"]
    assert evs[1].business_id == bid and evs[1].detail["map"] is True and "not written to Yext" in evs[1].detail["note"]
    st = client.get("/api/room/state").json()
    assert st["counts"]["answered"] == 1 and st["latest"][0]["answer"] == "9-13"
    assert json.loads((TMP / "room_state.json").read_text())["answers"][bid]["display"] == "9-13"


def test_answer_parsing_and_unknown_business(client):
    assert room.parse_answer("Suljettu")["kind"] == "closed"
    assert room.parse_answer("Normaalisti")["kind"] == "regular"
    assert room.parse_answer("10–14")["display"] == "10-14"
    assert room.parse_answer("<b>moi</b>")["display"] == "bmoib"
    assert room.parse_answer("9:30 - 13.00 !?;/")["display"] == "9:30-13"
    assert client.post("/api/room/answer", json={"business_id": "nope", "answer": "9-13"}).status_code == 404


def test_reset(client):
    client.get("/join")
    bid = room.assign(client.cookies["kaiku_room"])["id"]
    assert client.post("/api/room/answer", json={"business_id": bid, "answer": "Suljettu"}).status_code == 200
    assert client.get("/api/room/state").json()["counts"]["answered"] == 1
    assert client.get("/api/room/reset").status_code == 403
    assert client.get("/api/room/reset?key=wrong").status_code == 403
    assert client.get("/api/room/state").json()["counts"]["answered"] == 1
    assert client.get("/api/room/reset?key=sekret").json()["ok"] is True
    assert client.get("/api/room/state").json()["counts"]["answered"] == 0


def test_pages_render(client):
    m = client.get("/map")
    assert m.status_code == 200 and "OpenStreetMap (real)" in m.text and "map.js" in m.text
    r = client.get("/room")
    assert r.status_code == 200 and "Scan to take over a business" in r.text and "Become a Turku business owner" in r.text
    q = client.get("/api/room/qr.svg")
    assert q.status_code == 200 and "<svg" in q.text
    for t in (m.text, r.text, client.get("/join").text):
        assert "—" not in t and "–" not in t


def test_answer_requires_cookie_ownership(client):
    client.get("/join")
    mine = room.assign(client.cookies["kaiku_room"])["id"]
    other = next(b["id"] for b in room.businesses() if b["id"] != mine)
    r = client.post("/api/room/answer", json={"business_id": other, "answer": "9-13"})
    assert r.status_code == 403 and "ei ole sinun" in r.json()["fi"] and "not yours" in r.json()["en"]
    stranger = TestClient(app)  # no cookie at all
    assert stranger.post("/api/room/answer", json={"business_id": mine, "answer": "9-13"}).status_code == 403
    assert client.get("/api/room/state").json()["counts"]["answered"] == 0
    assert client.post("/api/room/answer", json={"business_id": mine, "answer": "9-13"}).status_code == 200


def test_answer_rate_limit_3_per_minute(client):
    client.get("/join")
    bid = room.assign(client.cookies["kaiku_room"])["id"]
    codes = [client.post("/api/room/answer", json={"business_id": bid, "answer": f"{i}-17"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_free_text_whitelist_and_escape(client):
    assert room.parse_answer("a<script>alert(1)</script>&\"'")["display"] == "ascriptalert1script"
    assert len(room.parse_answer("x" * 100)["display"]) == 40
    client.get("/join")
    bid = room.assign(client.cookies["kaiku_room"])["id"]
    client.post("/api/room/answer", json={"business_id": bid, "answer": "<img src=x onerror=1>"})
    assert "<img" not in client.get("/join").text


def test_reset_link_needs_key(client):
    assert "sekret" not in client.get("/room?key=sekret").text  # the key never sits in the HTML; the page sends it as a header
    assert client.get("/api/room/reset").status_code == 403
