import json
import os
import tempfile
import time
from pathlib import Path

import pytest

os.environ["KAIKU_DB"] = str(Path(tempfile.mkdtemp()) / "t.sqlite")
os.environ["KAIKU_STEP_GAP"] = "0"
os.environ["OWNER_WHATSAPP"] = "+358000000000"

from fastapi.testclient import TestClient  # noqa: E402

from kaiku import chain, events, store  # noqa: E402
from kaiku.app import app  # noqa: E402
from kaiku.config import settings  # noqa: E402
from kaiku.schema import ApplyResult, Decision, Detection, Event, Suggestion  # noqa: E402

settings.STEP_GAP = 0
settings.STUB_DECIDE = "auto"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_schema_round_trip():
    s = Suggestion(id="a", business_id="x", holiday_date="2026-12-24", kind="hours",
                   proposed=[{"start": "09:00", "end": "13:00"}], confidence=0.9)
    assert Suggestion.model_validate_json(s.model_dump_json()) == s
    d = Decision(suggestion_id="a", action="edit", edited="closed", via="voice")
    assert Decision.model_validate(json.loads(d.model_dump_json())).edited == "closed"
    assert ApplyResult(suggestion_id="a", yext_status="ok").publishers == []
    Detection(business_id="x", holiday_date="2026-12-24")
    with pytest.raises(Exception):
        Suggestion(id="a", business_id="x", holiday_date="d", kind="hours", confidence=1.5)


def test_store_seed():
    b = store.seed(force=True)
    assert b.id == "furry-paw" and b.source == "yext-sandbox" and b.owner_whatsapp == "+358000000000"
    assert len(b.last_year_exceptions) == 10 and b.regular_hours["sun"] == []
    assert store.get_business("furry-paw").name == "Furry Paw Vet Clinic"
    raw = json.loads((settings.DATA_DIR / "furry_paw.json").read_text())
    assert raw["owner_whatsapp"] is None and "Fictional" in raw["note"]


def test_healthz_and_home(client):
    assert client.get("/healthz").json() == {"ok": True, "broker": "unknown"}
    html = client.get("/").text
    for t in ["hero", "event-strip", "business-card", "run-chain"]:
        assert f'data-pilot="{t}"' in html
    assert "Furry Paw Vet Clinic" in html and "SAMPLE HISTORY" in html
    assert "—" not in html
    assert client.get("/static/horizon.css").status_code == 200
    assert client.get("/static/fonts/Newsreader.ttf").status_code == 200
    assert client.get("/api/today").json()["label_fi"].startswith("Tänään:")


def test_events_recent_and_sse_replay(client):
    events.emit(Event(step="detect", business_id="furry-paw", title_fi="testi", title_en="test"))
    rec = client.get("/api/events/recent?limit=5").json()
    assert rec and rec[-1]["title_en"] == "test"
    import asyncio

    async def first_chunks():  # call the endpoint directly: TestClient streaming hangs on some starlette versions
        r = await events.stream(replay=1, last=1)
        assert r.media_type.startswith("text/event-stream")
        got = ""
        async for chunk in r.body_iterator:
            got += chunk if isinstance(chunk, str) else chunk.decode()
            if "data:" in got:
                break
        await r.body_iterator.aclose()
        return got
    got = asyncio.run(first_chunks())
    assert "event: kaiku" in got and '"title_en":"test"' in got


def test_registry_rejects_unknown_step():
    with pytest.raises(ValueError):
        chain.register("nope", lambda: None)


# ---------- wiring tests (fakes: fallback broker, fake Yext, no network, no WhatsApp) ----------
from datetime import date  # noqa: E402

from kaiku.broker.fallback import FallbackBroker  # noqa: E402
from kaiku.learn import timetravel  # noqa: E402

HOURS_13 = [{"start": "09:00", "end": "13:00"}]


@pytest.fixture(scope="module", autouse=True)
def _module_fakes():
    mp = pytest.MonkeyPatch()
    fb = FallbackBroker()
    mp.setattr(chain, "get_broker", lambda: fb)
    mp.setattr(chain, "whatsapp_configured", lambda: False)
    mp.setattr(chain, "yext_reset", lambda: {"holidayHours": []})
    from kaiku.detect import signals
    mp.setattr(signals, "website", lambda b, h: None)
    mp.setattr(signals, "google_now", lambda b, d: {"status": "unknown"})
    yield fb
    mp.undo()


@pytest.fixture
def wired(monkeypatch, tmp_path, _module_fakes):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_URL", "https://kaiku.example")
    calls = []

    def fake_apply(entity, day, proposed):
        calls.append((entity, day, proposed))
        return {"yext_status": "ok", "entity_id": entity, "date": day, "written": {"date": day}, "verified": True,
                "entity_version": "t0", "environment": "sandbox"}

    monkeypatch.setattr(chain, "apply_backend", fake_apply)
    monkeypatch.setattr(chain, "STUB_DECIDE_DELAY", 0)
    monkeypatch.setitem(chain.STEPS, "decide", chain.decide)  # the stub: auto-approve at once
    timetravel.set_today(date(2026, 12, 17))
    store.clear_runs("furry-paw")
    store.seed(force=True)
    _module_fakes.__init__()  # fresh in-memory broker
    yield calls
    timetravel.clear()


def _run(client, day, until="learn", timeout=15):
    sid = client.post(f"/api/run?business=furry-paw&date={day}").json()["suggestion_id"]
    end = time.time() + timeout
    while time.time() < end:
        evs = [e for e in client.get("/api/events/recent?limit=100").json() if e["suggestion_id"] == sid]
        if any(e["step"] == until for e in evs):
            return sid, evs
        time.sleep(0.1)
    raise AssertionError("chain did not reach " + until)


def test_chain_end_to_end_with_fakes(client, wired, _module_fakes):
    sid, evs = _run(client, "2026-12-24")
    steps = [e["step"] for e in evs if e["step"] != "broker"]
    assert steps[:2] == ["detect", "suggest"] and steps[-1] == "learn"
    for want in ["detect", "suggest", "contact", "decide", "apply", "learn"]:
        assert want in steps
    s = client.get(f"/api/suggestions/{sid}").json()
    assert s["kind"] == "hours" and s["proposed"] == HOURS_13 and s["confidence"] == 0.75 and s["status"] == "applied"
    assert s["decide_url"].startswith("https://kaiku.example/d/")
    contact = next(e for e in evs if e["step"] == "contact")
    assert contact["title_fi"] == "WhatsApp ei ole vielä käytössä, päätöslinkki valmis"
    assert contact["title_en"] == "WhatsApp not configured yet, decision link ready"
    assert contact["detail"]["decide_url"] == s["decide_url"] and "24.12." in contact["detail"]["message_fi"]
    assert wired == [("SinceAI07", "2026-12-24", HOURS_13)]
    apply_ev = next(e for e in evs if e["step"] == "apply")
    assert apply_ev["detail"]["verified"] is True and len(apply_ev["detail"]["where_it_shows"]) >= 4
    ent = _module_fakes.get_entity("urn:ngsi-ld:Store:furry-paw")
    inst = {i.get("datasetId", "default"): i["value"] for i in ent["holidayHours"]}
    assert inst["urn:ngsi-ld:dataset:kaiku:proposed"]["hours"] == HOURS_13 and inst["default"]["hours"] == HOURS_13
    assert any(e["step"] == "broker" for e in evs)


def test_decline_skips_apply(client, wired, monkeypatch):
    async def decline(s):
        return Decision(suggestion_id=s.id, action="decline", reason_chip="Ajat ovat väärin")
    monkeypatch.setitem(chain.STEPS, "decide", decline)
    sid, evs = _run(client, "2026-12-24")
    assert wired == []
    assert not any(e["step"] == "apply" for e in evs)
    assert client.get(f"/api/suggestions/{sid}").json()["status"] == "declined"
    learn = next(e for e in evs if e["step"] == "learn")
    assert "hylättiin" in learn["title_fi"]


def test_edit_applies_edited_hours(client, wired, monkeypatch):
    async def edit(s):
        return Decision(suggestion_id=s.id, action="edit", edited=[{"start": "10:00", "end": "14:00"}])
    monkeypatch.setitem(chain.STEPS, "decide", edit)
    _run(client, "2026-12-24")
    assert wired == [("SinceAI07", "2026-12-24", [{"start": "10:00", "end": "14:00"}])]


def test_no_change_path(client, wired):
    timetravel.set_today(date(2026, 11, 2))
    sid, evs = _run(client, "2026-11-08")
    s = client.get(f"/api/suggestions/{sid}").json()
    assert s["kind"] == "no_change" and s["proposed"] is None and wired == []
    assert next(e for e in evs if e["step"] == "decide")["detail"]["phase"] == "skipped"


def test_on_decision_resolves_stub_waiter(client, wired):
    import asyncio

    async def go():
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        chain._waiters["zz"] = fut
        assert await chain.on_decision({"suggestion_id": "zz", "action": "approve"})
        return fut.result().action
    assert asyncio.run(go()) == "approve"


def test_status_and_reset_shapes(client, wired):
    st = client.get("/api/status").json()
    assert set(st) == {"broker", "whatsapp_configured", "yext_entity", "today", "public_url", "voice"}
    assert st["broker"] in ("orion-ld", "fallback") and st["yext_entity"] == "SinceAI07" and st["whatsapp_configured"] is False
    timetravel.set_today(date(2026, 5, 1))
    _run(client, "2026-12-24")
    assert client.post("/api/reset").status_code == 403
    assert client.post("/api/reset?key=wrong").status_code == 403
    assert client.post("/api/reset", headers={"X-Kaiku-Key": "wrong"}).status_code == 403
    r = client.post("/api/reset?key=testkey").json()
    assert client.post("/api/reset", headers={"X-Kaiku-Key": "testkey"}).status_code == 200
    assert r["today"] == "2026-12-17" and r["reset"]["yext_holiday_rows"] == 0 and r["reset"]["broker_reset"] is True
    assert client.get("/api/suggestions?business=furry-paw").json() == []
    assert client.get("/api/events/recent?limit=10").json() == []
    ent = chain.get_broker().get_entity("urn:ngsi-ld:Store:furry-paw")
    assert ent["holidayHoursStatus"]["value"]["status"] == "missing"
    inst = {i.get("datasetId", "default"): i["value"] for i in ent["holidayHours"]}
    ds = "urn:ngsi-ld:dataset:kaiku:"
    assert "urn:ngsi-ld:dataset:kaiku:proposed" not in inst
    assert inst[ds + "lastyear"]["hours"] == [{"start": "09:00", "end": "13:00"}] and inst[ds + "lastyear"]["date"] == "2025-12-24"
    assert inst[ds + "website"]["hours"] == "unknown" and inst[ds + "google"]["hours"] == "unknown" and ds + "peers" in inst
    assert inst["default"]["hours"] == [{"start": "09:00", "end": "17:00"}] and inst["default"]["date"] == "2026-12-24"


def test_run_validates_input(client, wired):
    for bad in ["garbage", "2026-13-40", "2024-12-24", "2028-01-01", "2026-W52-3", "20261224", ""]:
        r = client.post(f"/api/run?business=furry-paw&date={bad}")
        assert r.status_code == 400 and "Virheellinen" in r.json()["detail"] and "Invalid date" in r.json()["detail"], bad
    r = client.post("/api/run?business=nope&date=2026-12-24")
    assert r.status_code == 400 and "Unknown business" in r.json()["detail"]


def test_one_broker_event_before_detect(client, wired):
    sid, evs = _run(client, "2026-12-24")
    allev = client.get("/api/events/recent?limit=100").json()
    first_detect = next(i for i, e in enumerate(allev) if e["step"] == "detect")
    pre = [e for e in allev[:first_detect] if e["step"] == "broker"]
    assert len(pre) == 1 and pre[0]["title_fi"] == "Tilaus laukesi: 24.12. aukioloajat puuttuvat"
    assert pre[0]["title_en"] == "Subscription fired: 24.12. hours missing" and pre[0]["detail"]["date"] == "2026-12-24"


def test_emit_once_dedupes():
    from kaiku.broker import router as br
    br.reset_dedupe()
    assert br.emit_once("missing", "x", "2026-12-24") is True
    assert br.emit_once("missing", "x", "2026-12-24") is False
    assert br.emit_once("missing", "x", "2026-12-25") is True
