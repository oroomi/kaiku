import json
from pathlib import Path

import pytest

from kaiku.detect import holidays as hol
from kaiku.detect import signals as sg
from kaiku.detect.engine import detect
from kaiku.suggest import backtest
from kaiku.suggest.engine import ASK_BELOW, suggest
from kaiku.suggest.schema import Business

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "data" / "sample_cases.json").read_text())["cases"]


def run(c):
    b = Business.from_dict(c["business"])
    return b, suggest(b, detect(b, c["date"], c["today"], use_network=False))


@pytest.mark.parametrize("c", CASES, ids=[c["case"][:2].strip() for c in CASES])
def test_ten_cases(c):
    _, s = run(c)
    assert s.kind == c["expect_kind"], c["case"]
    assert "—" not in s.message_fi and "–" not in s.message_fi
    if s.kind == "ask":
        assert s.question_fi and s.question_fi in s.message_fi
        assert s.proposed is None
    for r in s.reasons:
        assert set(r) == {"source", "dataset_id", "text_fi", "text_en"}
        assert r["dataset_id"].startswith("urn:ngsi-ld:dataset:kaiku:")


def test_backtest_sample_metrics():
    res = backtest.run(backtest.load_cases(ROOT / "data" / "sample_cases.json"))
    m = backtest.metrics(res)
    assert m["wrong_suggestion_rate"] == 0.0 and m["abstain_rate"] == 0.2 and m["closed_day_accuracy"] == 1.0


def test_gate_no_guess_above_threshold_on_cold_start():
    for c in CASES:
        b, s = run(c)
        if not b.last_year_exceptions and s.kind in ("hours", "closed"):
            assert s.confidence >= ASK_BELOW  # only the "public holiday and prior closed" rule may propose
            assert s.kind == "closed"
        if s.kind == "ask":
            assert s.confidence < ASK_BELOW


def test_hero_message_snapshot():
    _, s = run(CASES[0])
    assert s.message_fi == ("Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Viime vuonna olitte auki 9-13, mutta "
                            "tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Google näyttää nyt tavalliset "
                            "torstain aukioloajat (9-17). Ehdotus: to 24.12. klo 9-13.")
    assert s.proposed == [{"start": "09:00", "end": "13:00"}] and s.confidence == 0.75


def test_ask_question_shape():
    _, s = run(CASES[3])
    assert s.question_fi == "Oletteko auki jouluaattona 24.12.? Vastaa esimerkiksi 9-13 tai suljettu."


def test_same_weekday_confidence():
    c = json.loads(json.dumps(CASES[0]))
    # 2025-11-01 and 2026-10-31 are both Saturdays; make the exception differ from regular so it is proposed
    c["business"]["last_year_exceptions"] = [{"date": "2025-11-01", "hours": [{"start": "11:00", "end": "13:00"}]}]
    c["date"], c["today"] = "2026-10-31", "2026-10-24"
    _, s = run(c)
    assert s.kind == "hours" and s.confidence == 0.85


def test_exception_already_set_is_no_change():
    c = json.loads(json.dumps(CASES[0]))
    c["business"]["exceptions"] = [{"date": "2026-12-24", "hours": [{"start": "09:00", "end": "13:00"}]}]
    _, s = run(c)
    assert s.kind == "no_change" and s.confidence == 0.95


def test_holidays():
    h = hol.get("2026-11-08")
    assert h.name_fi == "Isänpäivä" and h.public_holiday is False
    assert hol.get("2026-12-24").public_holiday is True
    assert hol.get("2027-01-06").name_fi == "Loppiainen"
    names = {x.name_fi for x in hol.upcoming("2026-12-17", 21)}
    assert {"Jouluaatto", "Joulupäivä", "Tapaninpäivä", "Uudenvuodenaatto"} <= names
    assert hol.same_holiday_previous_year(hol.get("2026-04-05")).date == "2025-04-20"  # moveable: by name


def test_website_signal_and_dead_site(monkeypatch):
    b = Business.from_dict(CASES[0]["business"])
    h = hol.get("2026-12-24")
    assert sg.website(b, h, timeout=1) is None  # furrypaw.example does not resolve

    class R:
        status_code = 200
        text = "<html><p>Poikkeusaukioloajat</p><p>Jouluaatto 24.12. klo 10-12</p><p>Joulupäivä suljettu</p></html>"

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    w = sg.website(b, h)
    assert w["hours"] == [{"start": "10:00", "end": "12:00"}] and "Jouluaatto" in w["quote"]
    s = suggest(b, detect(Business.from_dict({**CASES[0]["business"], "last_year_exceptions": []}), "2026-12-24"))
    assert s.kind == "hours" and s.confidence == 0.8


def test_google_unknown_without_key(monkeypatch):
    monkeypatch.setattr(sg, "_env_key", lambda n: None)
    assert sg.google_now(Business.from_dict(CASES[0]["business"]), "2026-12-24") == {"status": "unknown"}


def test_csv_loader(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("business_id,toimiala,regular_hours,last_year_exception,date,target\n"
                 "x1,cafe,mon-fri 09:00-17:00; sat 10:00-14:00,9-13,2026-12-24,9-13\n")
    res = backtest.run(backtest.load_cases(p))
    assert res[0]["correct"] and res[0]["kind"] == "hours"
