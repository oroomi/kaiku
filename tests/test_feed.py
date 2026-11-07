from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.detect import signals as sg
from kaiku.suggest import feed


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(sg, "website", lambda b, h, timeout=5.0: None)
    monkeypatch.setattr(sg, "google_now", lambda b, d: {"status": "unknown"})
    from kaiku.learn import prefs
    monkeypatch.setattr(prefs, "get_prefs", lambda bid: {"standing_permission": None})


def kinds(f, d=None):
    return [c["kind"] for c in f["suggestions"] if d is None or c.get("holiday_date") == d]


def test_christmas_eve_holiday_hours_and_conflict(monkeypatch):
    monkeypatch.setattr(sg, "website", lambda b, h, timeout=5.0: {"hours": [{"start": "09:00", "end": "13:00"}], "quote": "24.12. klo 9-13"} if h.date == "2026-12-24" else None)
    monkeypatch.setattr(sg, "google_now", lambda b, d: {"status": "shows_hours", "text": "9-17", "hours": [{"start": "09:00", "end": "17:00"}]} if str(d) == "2026-12-24" else {"status": "unknown"})
    f = feed.build_feed("furry-paw", date(2026, 12, 24), use_network=True, extra_loaders=False)
    assert f["today"] == "2026-12-24" and f["business_id"] == "furry-paw"
    ks = kinds(f, "2026-12-24")
    assert "holiday_hours" in ks and "conflict" in ks
    c = next(c for c in f["suggestions"] if c["kind"] == "conflict")
    assert {s["source"] for s in c["sources"]} == {"lastyear", "website", "google"}
    assert all(s["dataset_id"].startswith("urn:ngsi-ld:dataset:kaiku:") for s in c["sources"])
    assert c["proposed"] == [{"start": "09:00", "end": "13:00"}] and c["confidence"] == 0.75
    assert c["title_en"] == "Your sources disagree about 24.12."


def test_no_conflict_without_disagreement():
    f = feed.build_feed("furry-paw", date(2026, 12, 24), extra_loaders=False)
    assert "conflict" not in kinds(f)


def test_fathers_day_is_no_change():
    f = feed.build_feed("furry-paw", date(2026, 11, 8), use_network=False)
    c = next(c for c in f["suggestions"] if c.get("holiday_date") == "2026-11-08")
    assert c["kind"] == "no_change" and c["proposed"] is None and c["reasons"]
    assert "Father" in c["title_en"]


def test_period_card_on_17_dec():
    f = feed.build_feed("furry-paw", date(2026, 12, 17), use_network=False)
    p = next(c for c in f["suggestions"] if c["kind"] == "period")
    assert p["title_en"].startswith("Christmas period: ") and p["standing_permission_offered"]
    assert "Want me to handle this period every year?" in p["text_en"]
    assert [x["date"] for x in p["proposed"]][0] == "2026-12-24"
    assert next(x for x in p["proposed"] if x["date"] == "2026-12-25")["proposed"] == "closed"
    assert p["period"] == {"key": "christmas", "start": "2026-12-24", "end": "2027-01-06"}


def test_stable_fields_and_no_em_dash():
    f = feed.build_feed("furry-paw", date(2026, 12, 17), use_network=False)
    need = {"id", "kind", "title_en", "text_en", "title_fi", "text_fi", "proposed", "confidence", "reasons", "status"}
    for c in f["suggestions"]:
        assert need <= set(c)
        for r in c["reasons"]:
            assert {"source", "dataset_id", "text_en", "text_fi"} <= set(r)
        assert "—" not in c["text_en"] + c["text_fi"]


def test_unknown_business():
    assert feed.build_feed("nope", date(2026, 12, 1))["suggestions"] == []


class FakeClient:
    def __init__(self, desc, reviews):
        self.desc, self.reviews = desc, reviews

    def get_entity(self, i):
        e = {"name": "Furry Paw Vet Clinic", "address": {"line1": "Tikkurilantie 9", "city": "Vantaa"}, "categories": {"fonecta": ["E1700"]}}
        if self.desc:
            e["description"] = self.desc
        return e

    def list_reviews(self, i):
        return self.reviews


def test_loaders_return_nothing_without_data():
    c = FakeClient("A clean description.", [])
    assert feed.description_loader("furry-paw", date(2026, 11, 6), c) == []   # present and clean: no card
    assert all(x["reasons"][0]["source"] == "sample_reviews" for x in feed.review_loader("furry-paw", date(2026, 11, 6), c))  # empty sandbox: labelled sample file


def test_loaders_use_real_values_only():
    c = FakeClient("We offer vacination.", [{"id": 7, "rating": 2, "content": "Long wait."}, {"id": 8, "rating": 5, "content": "Great"}])
    assert feed.description_loader("furry-paw", date(2026, 11, 6), c)[0]["proposed"] == "We offer vaccination."
    r = feed.review_loader("furry-paw", date(2026, 11, 6), c)
    assert [x["rating"] for x in r] == [2, 5] and "Long wait." in r[0]["text_en"]


def test_endpoint():
    from kaiku.suggest.router import router
    app = FastAPI()
    app.include_router(router)
    cl = TestClient(app)
    r = cl.get("/api/feed/furry-paw?date=2026-11-08&network=0")
    assert r.status_code == 200 and r.json()["suggestions"][0]["kind"] == "no_change"
    assert cl.get("/api/feed/furry-paw?date=bad").status_code == 400
    assert cl.get("/api/feed/zzz?date=2026-11-08&network=0").status_code == 404
