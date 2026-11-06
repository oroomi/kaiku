import importlib
from datetime import date

import pytest


EMITTED = []


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    try:  # keep the shared app sqlite clean: capture learn events instead of persisting
        from kaiku import events
        monkeypatch.setattr(events, "emit", lambda e: EMITTED.append(e) or e)
    except Exception:
        pass
    EMITTED.clear()
    yield tmp_path


def sug(**kw):
    s = {"id": "sug-x-2026-12-24", "business_id": "b1", "holiday_date": "2026-12-24", "kind": "hours",
         "proposed": [{"start": "09:00", "end": "13:00"}], "confidence": 0.85,
         "holiday": {"name_fi": "Jouluaatto"}, "reason_fi": "Viime vuonna 24.12. olitte auki 9-13."}
    s.update(kw)
    return s


def prefs():
    from kaiku.learn import prefs as p
    return p


def test_edit_then_next_cycle_proposes_edited():
    p = prefs()
    e = [{"start": "10:00", "end": "14:00"}]
    p.record_decision("b1", sug(), {"action": "edit", "edited": e})
    orig = sug(confidence=0.7)
    out = p.apply_prefs("b1", orig)
    assert out["proposed"] == e and out["confidence"] == 0.9 and out is not orig
    assert orig["proposed"][0]["end"] == "13:00"
    assert "Viime vuonna muokkasit tämän ajaksi 10-14" in out["reason_fi"]
    assert "edited" in out["reason_en"]
    assert "—" not in out["reason_fi"] and "–" not in out["reason_fi"]
    assert p.get_prefs("b1")["edits_by_weekday"]["jouluaatto|thu"]["hours"] == e


def test_edit_to_closed():
    p = prefs()
    p.record_decision("b1", sug(), {"action": "edit", "edited": "closed"})
    out = p.apply_prefs("b1", sug())
    assert out["kind"] == "closed" and out["proposed"] is None


def test_decline_twice_suppresses():
    p = prefs()
    for _ in range(2):
        p.record_decision("b1", sug(), {"action": "decline", "reason_chip": "suljettu"})
    out = p.apply_prefs("b1", sug())
    assert out["kind"] == "no_change" and out["reason_fi"] == "Olet hylännyt tämän ehdotuksen kahdesti"
    assert p.get_prefs("b1")["declines"]["jouluaatto"]["count"] == 2


def test_decline_once_lowers_confidence():
    p = prefs()
    p.record_decision("b1", sug(), {"action": "decline", "reason_chip": "x"})
    out = p.apply_prefs("b1", sug())
    assert out["confidence"] == pytest.approx(0.70) and out["kind"] == "hours"


def test_other_business_and_holiday_unaffected():
    p = prefs()
    p.record_decision("b1", sug(), {"action": "decline"})
    assert p.apply_prefs("b2", sug())["confidence"] == 0.85
    other = sug(holiday={"name_fi": "Uudenvuodenpäivä"}, holiday_date="2027-01-01")
    assert p.apply_prefs("b1", other)["confidence"] == 0.85


def test_standing_permission_same_holiday_and_all():
    p = prefs()
    p.record_decision("b1", sug(), {"action": "approve", "standing_permission": True})
    assert p.apply_prefs("b1", sug())["auto_apply"] is True
    assert "auto_apply" not in p.apply_prefs("b1", sug(holiday={"name_fi": "Pääsiäinen"}, holiday_date="2027-03-28"))
    p.record_decision("b2", sug(), {"action": "approve", "standing_permission": True, "scope": "all"})
    out = p.apply_prefs("b2", sug(holiday={"name_fi": "Pääsiäinen"}, holiday_date="2027-03-28"))
    assert out["auto_apply"] and "pysyvän luvan" in out["auto_apply_reason_fi"]
    assert "—" not in out["auto_apply_reason_fi"]


def test_timetravel_across_fresh_imports(monkeypatch):
    from kaiku.learn import timetravel as t1
    assert not t1.is_fake()
    t1.set_today(date(2026, 12, 17))
    t2 = importlib.reload(importlib.import_module("kaiku.learn.timetravel"))
    assert t2.today() == date(2026, 12, 17) and t2.now().date() == date(2026, 12, 17)
    assert t2.now().tzinfo is not None
    t2.clear()
    assert not t1.is_fake() and t1.today() == t1.now().date()


def test_files_in_data_dir(datadir):
    from kaiku.learn import timetravel as t
    t.set_today(date(2026, 11, 2))
    prefs().record_decision("b1", sug(), {"action": "decline"})
    assert (datadir / "timetravel.json").exists() and (datadir / "learn_prefs.json").exists()


def test_router():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kaiku.learn.router import router
    app = FastAPI(); app.include_router(router)
    c = TestClient(app)
    assert c.get("/api/timetravel").json()["fake"] is False
    assert c.get("/api/timetravel?date=2026-12-17").json() == {"today": "2026-12-17", "fake": True}
    assert c.get("/api/timetravel").json()["today"] == "2026-12-17"
    assert c.get("/api/timetravel?date=real").json()["fake"] is False
    assert c.post("/api/timetravel?date=2026-11-02").json()["today"] == "2026-11-02"
    assert c.post("/api/timetravel?date=").json()["fake"] is False
    assert c.get("/api/timetravel?date=nonsense").status_code == 400
    e = [{"start": "10:00", "end": "14:00"}]
    r = c.post("/api/learn/decision", json={"business_id": "b1", "suggestion": sug(), "decision": {"action": "edit", "edited": e}}).json()
    assert r["suggestion"]["proposed"] == e and r["prefs"]["edits"]["jouluaatto"]["hours"] == e
    assert c.get("/api/learn/prefs/b1").json()["edits"]["jouluaatto"]


def test_event_emitted():
    pytest.importorskip("fastapi")
    prefs().record_decision("b1", sug(), {"action": "decline"})
    assert EMITTED and EMITTED[0].step == "learn" and "hylättiin" in EMITTED[0].title_fi
