import asyncio
import json
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.schema import Decision, Event


def test_as_date_normalises_datetime():
    from kaiku.detect.engine import _as_date
    assert _as_date(datetime(2026, 12, 17, 10, 30)) == date(2026, 12, 17)
    assert type(_as_date(datetime(2026, 12, 17, 10, 30))) is date
    assert _as_date("2026-12-17") == date(2026, 12, 17) and _as_date(None) is None


def test_broker_notify_realistic_payload_emits_event(monkeypatch):
    from kaiku import events
    got = []
    monkeypatch.setattr(events, "emit", lambda e: got.append(e) or e)
    from kaiku.broker.router import router
    app = FastAPI(); app.include_router(router)
    note = {"id": "urn:ngsi-ld:Notification:1", "type": "Notification", "subscriptionId": "urn:ngsi-ld:Subscription:kaiku-holiday-hours-missing",
            "notifiedAt": "2026-11-06T12:00:00.000Z",
            "data": [{"id": "urn:ngsi-ld:Store:furry-paw", "type": "Store",
                      "holidayHoursStatus": {"type": "Property", "value": {"date": "2026-12-24", "status": "missing"},
                                             "observedAt": "2026-11-06T12:00:00.000Z"}}]}
    r = TestClient(app).post("/broker/notify", json=note)
    assert r.status_code == 200 and r.json()["fired"][0]["kind"] == "missing"
    assert any(e.step == "broker" and "Subscription fired" in e.title_en for e in got)


def test_decision_carries_scope_to_learn(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    from kaiku import chain
    from kaiku.decide import step
    from kaiku.learn import prefs
    d = step._to_decision("sg-s", {"action": "approve", "standing_permission": True, "scope": "all"})
    assert d.scope == "all" and Decision(suggestion_id="x", action="approve").scope == "same"
    s = chain.Suggestion(id="sg-s", business_id="b1", holiday_date="2026-12-24", kind="hours",
                         proposed=[{"start": "09:00", "end": "13:00"}], confidence=0.9)
    chain.learn_real(s, d)
    allp = json.loads((tmp_path / "learn_prefs.json").read_text())
    assert json.dumps(allp).count('"scope": "all"') == 1


def test_chain_timeout_skips_apply_and_learn(monkeypatch, tmp_path):
    from kaiku import chain, store
    from kaiku.learn import timetravel
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    from kaiku.detect import signals
    monkeypatch.setattr(signals, "website", lambda b, h: None)
    monkeypatch.setattr(signals, "google_now", lambda b, d: {"status": "unknown"})
    monkeypatch.setattr(chain, "whatsapp_configured", lambda: False)
    calls, evs = [], []

    def fake_apply(*a, **k):
        calls.append(a); return {}
    monkeypatch.setattr(chain, "apply_backend", fake_apply)
    async def to(s):
        return Decision.model_construct(suggestion_id=s.id, action="timeout", edited=None, reason_chip=None,
                                        standing_permission=False, scope="same", via="web", at="")
    monkeypatch.setitem(chain.STEPS, "decide", to)
    monkeypatch.setattr(chain, "_ev", lambda step, b, sid, fi, en, **d: evs.append((step, fi, en, d)))
    timetravel.set_today(date(2026, 12, 17))
    store.seed(force=True)
    try:
        s = asyncio.run(chain.run_chain("furry-paw", "2026-12-24"))
    finally:
        timetravel.clear()
    assert calls == [] and not any(e[0] in ("apply", "learn") for e in evs)
    assert ("decide", "Omistaja ei vastannut ajoissa, ei muutoksia", "Owner did not answer in time, nothing changed") in [e[:3] for e in evs]
    assert store.get_suggestion(s.id).status == "expired"
