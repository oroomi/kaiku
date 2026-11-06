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
                            "tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset "
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


# ---- verifier fixes ------------------------------------------------------------------------------
import subprocess
import sys

FP = {"id": "fp", "name": "Furry Paw", "category": "veterinary",
      "regular_hours": {k: [{"start": "09:00", "end": "17:00"}] for k in ("mon", "tue", "wed", "thu", "fri")} | {"sat": [], "sun": []},
      "last_year_exceptions": [{"date": "2025-12-24", "hours": [{"start": "09:00", "end": "13:00"}]}]}


def sug(biz, date, today=None):
    b = Business.from_dict(biz)
    return suggest(b, detect(b, date, today, use_network=False))


def test_past_date_gives_no_suggestion():
    b = Business.from_dict(FP)
    det = detect(b, "2026-12-24", "2026-12-27", use_network=False)
    assert det.status == "past" and det.reason_codes == ["PAST_DATE"]
    s = suggest(b, det)
    assert s.kind == "no_change" and s.proposed is None and s.status == "expired" and s.confidence == 0.0
    assert "mennyt" in s.message_fi
    assert sug(FP, "2026-12-24", "2026-12-24").kind == "hours"  # today itself is still open
    assert sug(FP, "2026-12-24", None).kind == "hours"


def test_past_cli_prints_clearly():
    r = subprocess.run([sys.executable, "-m", "kaiku.suggest.cli", "--date", "2026-12-24", "--today", "2026-12-27",
                        "--no-network"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and "PAST:" in r.stdout and "jo mennyt" in r.stdout


def test_public_holiday_on_closed_weekday_is_true():
    s = sug(FP, "2026-12-06", "2026-11-30")  # Itsenäisyyspäivä on a Sunday, closed Sundays
    assert s.kind == "no_change" and s.proposed is None
    assert s.message_fi == "Itsenäisyyspäivä 6.12. on sunnuntai ja olette silloin kiinni, joten muutosta ei tarvita."
    assert "not a public holiday" not in s.message_en and "ei ole arkipyhä" not in s.message_fi
    assert all("ei ole arkipyhä" not in r["text_fi"] for r in s.reasons)


@pytest.mark.parametrize("bad", [[{"start": "13:00", "end": "09:00"}], [{"start": "9:00", "end": "13:00"}],
                                 [{"start": "09:00", "end": "09:00"}], [], [{"start": "25:00", "end": "26:00"}], "garbage"])
def test_invalid_last_year_never_proposed(bad):
    biz = {**FP, "last_year_exceptions": [{"date": "2025-12-24", "hours": bad}]}
    s = sug(biz, "2026-12-24", "2026-12-17")
    assert s.kind == "ask" and s.proposed is None and s.confidence < ASK_BELOW
    assert s.last_year_hours is None


def test_invalid_last_year_falls_through_to_next_signal(monkeypatch):
    biz = {**FP, "last_year_exceptions": [{"date": "2025-12-24", "hours": [{"start": "13:00", "end": "09:00"}]}]}
    b = Business.from_dict(biz)
    monkeypatch.setattr(sg, "website", lambda *a, **k: {"quote": "Jouluaatto 24.12. klo 10-12",
                                                        "hours": [{"start": "10:00", "end": "12:00"}], "url": "x"})
    s = suggest(b, detect(b, "2026-12-24", "2026-12-17", use_network=True))
    assert s.kind == "hours" and s.confidence == 0.8 and s.proposed == [{"start": "10:00", "end": "12:00"}]


def test_unknown_google_is_not_claimed():
    s = sug(FP, "2026-12-24", "2026-12-17")
    assert "Google näyttää" not in s.message_fi and "Google now shows" not in s.message_en
    assert "Fonecta Connect näyttää nyt tavalliset torstain aukioloajat (9-17)" in s.message_fi
    assert all("Google" not in r["text_fi"] for r in s.reasons)


def test_verified_google_is_named(monkeypatch):
    monkeypatch.setattr(sg, "google_now", lambda b, d: {"status": "shows_hours", "text": "9-17",
                                                        "hours": [{"start": "09:00", "end": "17:00"}]})
    b = Business.from_dict(FP)
    s = suggest(b, detect(b, "2026-12-24", "2026-12-17", use_network=True))
    assert "Google näyttää nyt tavalliset torstain aukioloajat (9-17)" in s.message_fi
    assert s.google_now["status"] == "shows_hours"


def test_cli_jsonl_flag_and_invalid_dates():
    r = subprocess.run([sys.executable, "-m", "kaiku.suggest.cli", "--date", "2026-12-24", "2026-12-25", "--today",
                        "2026-12-17", "--no-network", "--jsonl"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 2 and [json.loads(x)["holiday_date"] for x in lines] == ["2026-12-24", "2026-12-25"]
    for bad in ("garbage", "2026-13-40"):
        r = subprocess.run([sys.executable, "-m", "kaiku.suggest.cli", "--date", bad, "--no-network"],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 2 and "Traceback" not in r.stderr and len(r.stderr.strip().splitlines()) == 1
    r = subprocess.run([sys.executable, "-m", "kaiku.suggest.cli", "--date", "2026-12-24", "--today", "nope"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_contact_lane_fields_on_every_suggestion():
    keys = {"business_name", "holiday_name_fi", "holiday_name_en", "last_year_hours", "google_now", "decide_url"}
    for c in CASES:
        _, s = run(c)
        d = s.to_dict()
        assert keys <= set(d), c["case"]
        assert d["business_name"] == c["business"]["name"] and d["decide_url"] is None
        assert "status" in d["google_now"]
        assert d["last_year_hours"] is None or d["last_year_hours"] == "closed" or isinstance(d["last_year_hours"], list)
    d = run(CASES[0])[1].to_dict()
    assert d["holiday_name_fi"] == "Jouluaatto" and d["holiday_name_en"] == "Christmas Eve"
    assert d["last_year_hours"] == [{"start": "09:00", "end": "13:00"}]
    assert sug(FP, "2026-12-24", "2026-12-27").to_dict().keys() >= keys  # past path too


def test_holidays_survive_network_failure(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(hol, "_cache", None)
    old = tmp_path / "h.json"
    old.write_text(json.dumps({"holidays": [{"date": "2026-12-24", "name_fi": "Jouluaatto", "name_en": "Christmas Eve",
                                             "public_holiday": True, "weekday": "torstai"}]}))
    import os
    os.utime(old, (time.time() - 40 * 86400,) * 2)  # stale
    monkeypatch.setattr(hol, "CACHE", old)

    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(hol, "fetch_year", boom)
    assert [h.date for h in hol.all_holidays()] == ["2026-12-24"]  # kept the bundled file
    monkeypatch.setattr(hol, "_cache", None)
    monkeypatch.setattr(hol, "CACHE", tmp_path / "missing.json")
    assert any(h.name_fi == "Isänpäivä" for h in hol.all_holidays())  # no file, no network: still no crash
    monkeypatch.setattr(hol, "_cache", None)
