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
    with client.stream("GET", "/api/events?replay=1") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        got = ""
        for chunk in r.iter_text():
            got += chunk
            if "data:" in got:
                break
    assert "event: kaiku" in got and '"title_en":"test"' in got


def test_run_creates_events(client):
    sid = client.post("/api/run?business=furry-paw&date=2026-12-24").json()["suggestion_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        s = client.get(f"/api/suggestions/{sid}")
        if s.status_code == 200 and s.json()["status"] == "applied":
            break
        time.sleep(0.3)
    s = client.get(f"/api/suggestions/{sid}").json()
    assert s["kind"] == "hours" and s["proposed"] == [{"start": "09:00", "end": "13:00"}] and s["status"] == "applied"
    time.sleep(0.5)
    steps = [e["step"] for e in client.get("/api/events/recent?limit=50").json() if e["suggestion_id"] == sid]
    for want in ["detect", "suggest", "contact", "decide", "apply", "learn"]:
        assert want in steps
    assert client.get("/api/business/furry-paw").json()["id"] == "furry-paw"


def test_no_change_case_and_registry():
    b = store.get_business("furry-paw")
    s = chain.suggest(b, chain.detect(b, "2026-11-08", None))
    assert s.kind == "no_change" and s.proposed is None
    with pytest.raises(ValueError):
        chain.register("nope", lambda: None)
