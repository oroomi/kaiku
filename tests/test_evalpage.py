import io
import json

import pytest
from fastapi.testclient import TestClient

from kaiku.app import app
from kaiku.detect import holidays as hol
from kaiku.detect import signals as sg
from kaiku.evalpage import loader, runner
from kaiku.suggest import backtest as bt

client = TestClient(app)

CSV = """name,date,regular_hours,target
Cafe A,2026-12-24,mon-fri 09:00-17:00,9-13
Shop B,2026-12-25,mon-fri 09:00-17:00,closed
Vet C,2026-11-08,mon-fri 09:00-17:00,closed
"""


def post(content, name="d.csv", **data):
    return client.post("/api/eval/run", files={"file": (name, content, "text/plain")}, data=data)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used in an eval run")
    monkeypatch.setattr(sg, "website", boom)
    monkeypatch.setattr(sg, "google_now", boom)
    monkeypatch.setattr(hol, "build_cache", boom)
    import httpx
    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(httpx, "post", boom)


def test_page_renders_with_sample_and_label():
    r = client.get("/eval")
    assert r.status_code == 200
    assert "our own 10 sample cases" in r.text.lower() or "Our own 10 sample cases" in r.text
    assert "Download results (JSON lines, the Suggestion contract)" in r.text
    assert 'href="/eval"' in r.text


def test_sample_metrics_equal_backtest():
    expected = bt.metrics(bt.run(bt.load_cases(runner.SAMPLE)))
    d = client.get("/api/eval/sample").json()
    assert d["summary"]["metrics"] == expected
    assert len(d["rows"]) == 10
    assert all(r["reasons"] is not None for r in d["rows"])


def test_csv_with_target_gives_row_matches_and_matches_backtest(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(CSV)
    expected = bt.metrics(bt.run(bt.load_cases(p)))
    d = post(CSV).json()
    assert d["ok"] and d["kind"] == "csv"
    assert d["summary"]["metrics"] == expected
    assert [r["status"] for r in d["rows"]] == [
        "match" if x["correct"] else ("ask" if x["abstain"] else "miss") for x in bt.run(bt.load_cases(p))]
    assert d["mapping"]["name"] == "name" and d["mapping"]["regular"] == "regular_hours"
    assert d["rows"][0]["suggestion"]["kind"] in ("hours", "closed", "no_change", "ask")


def test_no_target_has_no_hit_rate():
    d = post("name,date,regular_hours\nA,2026-12-24,mon-fri 09:00-17:00\n").json()
    assert d["ok"] and d["summary"]["has_target"] is False and d["summary"]["metrics"] is None
    assert d["rows"][0]["status"] == "no_target"


def test_remap_columns():
    csv_text = "Firma,Paiva_x,Avoinna,Oikea\nCafe A,24.12.2026,mon-fri 09:00-17:00,9-13\n"
    first = post(csv_text)
    assert first.status_code == 400 and "date column" in first.json()["error"]
    assert first.json()["headers"] == ["Firma", "Paiva_x", "Avoinna", "Oikea"]
    d = post(csv_text, mapping=json.dumps({"name": "Firma", "date": "Paiva_x", "regular": "Avoinna", "target": "Oikea"})).json()
    assert d["ok"] and d["rows"][0]["business"] == "Cafe A" and d["rows"][0]["date"] == "2026-12-24"
    assert d["rows"][0]["target"] == "9-13"
    bad = post(csv_text, mapping=json.dumps({"date": "nope"}))
    assert bad.status_code == 400 and "nope" in bad.json()["error"]


def test_json_businesses_with_holidays():
    biz = [{"name": "Cafe", "category": "cafe", "regular_hours": {"mon": [{"start": "09:00", "end": "17:00"}]},
            "holidays": ["2026-12-24", "2026-12-25"]}]
    d = post(json.dumps(biz), "b.json").json()
    assert d["ok"] and d["kind"] == "json-businesses" and len(d["rows"]) == 2
    assert d["summary"]["has_target"] is False


def test_limits_and_malformed():
    big = "name,date\n" + "A,2026-12-24\n" * 200000
    r = post(big)
    assert r.status_code == 400 and "2 MB" in r.json()["error"]
    many = "name,date,regular_hours\n" + "A,2026-12-24,mon-fri 9-17\n" * 501
    r = post(many)
    assert r.status_code == 400 and "500" in r.json()["error"]
    assert post("{not json", "x.json").status_code == 400
    assert post("", "x.csv").status_code == 400
    assert post(b"\x00\x01\x02garbage", "x.csv").status_code == 400
    assert client.post("/api/eval/run", json={"a": 1}).status_code == 400
    assert client.post("/api/eval/run", files={"other": ("a.csv", "x")}).status_code == 400
    r = post("name,date\nA,not-a-date\n")
    assert r.status_code == 200 and r.json()["rows"][0]["status"] == "error"


def test_time_limit(monkeypatch):
    monkeypatch.setattr(runner, "TIME_LIMIT", -1)
    r = post(CSV)
    assert r.status_code == 400 and "seconds" in r.json()["error"]


def test_always_answer_flag(monkeypatch):
    base = {r["business"]: r for r in client.get("/api/eval/sample").json()["rows"]}
    asks = [r for r in base.values() if r["kind"] == "ask"]
    assert asks, "sample should contain an ask"
    monkeypatch.setenv("KAIKU_EVAL_ALWAYS_ANSWER", "1")
    d = client.get("/api/eval/sample").json()
    assert d["summary"]["always_answer"] and d["summary"]["asks"] == 0
    assert any(r["low_confidence"] for r in d["rows"])


def test_nothing_is_stored(tmp_path, monkeypatch):
    import os
    before = set(os.listdir(os.environ["KAIKU_DATA_DIR"]))
    post(CSV)
    assert set(os.listdir(os.environ["KAIKU_DATA_DIR"])) == before
