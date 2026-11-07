"""Listing score: checks and weights from a fake entity and a fake feed (docs/score.md)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.listing import router as listing
from kaiku.score import engine, router as score_router

DAY = {"openIntervals": [{"start": "09:00", "end": "17:00"}]}
ENTITY = {"name": "Furry Paw Vet Clinic", "meta": {"id": "SinceAI07"},
          "address": {"line1": "Tikkurilantie 9", "city": "Vantaa", "postalCode": "01300", "countryCode": "FI"},
          "categories": {"fonecta": ["E1700"]}, "description": "A small animal clinic in Vantaa.", "mainPhone": "+358401234567",
          "hours": {**{d: DAY for d in ("monday", "tuesday", "wednesday", "thursday", "friday")},
                    "saturday": {"openIntervals": [{"start": "10:00", "end": "14:00"}]}, "sunday": {"isClosed": True},
                    "holidayHours": [{"date": "2026-12-24", "openIntervals": [{"start": "09:00", "end": "13:00"}]},
                                     {"date": "2026-12-25", "isClosed": True}]}}
REVIEWS = {"count": 2, "averageRating": 4.0, "reviews": []}


def L(ent=None, rev=REVIEWS):
    return listing.normalise(ent or ENTITY, rev)


def card(i, kind, status="proposed", date="2026-12-24", proposed=None):
    return {"id": i, "kind": kind, "status": status, "holiday_date": date, "proposed": proposed, "title_en": i}


def feed(*cards):
    return {"suggestions": list(cards)}


def by(res):
    return {c["id"]: c for c in res["checks"]}


def test_weights_sum_to_100_and_every_check_has_a_source():
    r = engine.compute(L(), feed())
    assert sum(c["weight"] for c in r["checks"]) == 100 and len(r["checks"]) == 7
    assert all(c["source"] and c["label_en"] and c["detail_en"] for c in r["checks"])
    assert r["score"] == 100 and r["label_en"] == "Up to date" and r["checks_ok"] == 7 and r["pending"] == []


def test_holiday_hours_are_proportional():
    f = feed(card("a", "holiday_hours", "approved"), card("b", "holiday_hours", date="2026-12-25"),
             card("c", "holiday_hours", date="2026-12-31"), card("d", "holiday_hours", date="2027-01-06"))
    r = engine.compute(L(), f)
    h = by(r)["holidays"]
    assert h["points"] == 15 and h["weight"] == 30 and not h["ok"] and "2 of 4" in h["detail_en"] and "31.12." in h["detail_en"]
    assert r["score"] == 85   # 100 minus 15 of the 30 holiday points


def test_declined_holiday_counts_as_answered_and_no_holidays_is_full():
    f = feed(card("c", "holiday_hours", "declined", date="2026-12-31"))
    assert by(engine.compute(L(), f))["holidays"]["points"] == 30
    assert by(engine.compute(L(), feed()))["holidays"]["detail_en"] == "No upcoming holiday needs hours."
    e = {**ENTITY, "hours": {k: v for k, v in ENTITY["hours"].items() if k != "holidayHours"}}
    assert by(engine.compute(L(e), feed(card("a", "holiday_hours"))))["holidays"]["points"] == 0


def test_period_members_are_holidays():
    per = card("p", "period", proposed=[{"date": "2026-12-24", "kind": "hours"}, {"date": "2026-12-25", "kind": "closed"},
                                        {"date": "2026-12-26", "kind": "closed"}, {"date": "2026-12-27", "kind": "no_change"}])
    h = by(engine.compute(L(), feed(per)))["holidays"]
    assert h["points"] == 20 and "2 of 3" in h["detail_en"]   # 24 and 25 have rows, 26 does not; the no_change member is ignored


def test_missing_entity_data_costs_points():
    e = {k: v for k, v in ENTITY.items() if k not in ("description", "mainPhone", "categories")}
    c = by(engine.compute(L(e), feed()))
    assert c["description"]["points"] == 5 and c["contact"]["points"] == 0 and c["address"]["points"] == 0
    assert "No website and no phone" in c["contact"]["detail_en"]
    assert by(engine.compute(L({**ENTITY, "mainPhone": None, "websiteUrl": {"url": "https://x.fi"}}), feed()))["contact"]["ok"]
    nohrs = {**ENTITY, "hours": {"monday": DAY}}
    assert by(engine.compute(L(nohrs), feed()))["hours"]["points"] == 0


def test_pending_suggestions_cost_points_and_are_listed():
    f = feed(card("conf", "conflict"), card("desc", "description"), card("rev", "review"), card("n", "no_change", "info"))
    r = engine.compute(L(), f)
    c = by(r)
    assert c["agree"]["points"] == 0 and c["description"]["points"] == 10 and c["reviews"]["points"] == 0
    assert r["pending"] == ["conf", "desc", "rev"] and r["score"] == 60   # conflict -10, description -5, review -15; the conflict's date 24.12. has a row
    done = engine.compute(L(), feed(card("rev", "review", "approved")))
    assert by(done)["reviews"]["ok"]


def test_no_reviews_counts_as_ok():
    c = by(engine.compute(L(rev={"count": 0, "averageRating": 0.0}), feed()))["reviews"]
    assert c["ok"] and c["detail_en"] == "No reviews yet."


@pytest.fixture
def app(monkeypatch):
    class Fake:
        def get_entity(self, eid):
            assert eid == "SinceAI07"
            return ENTITY

        def _req(self, m, p):
            return REVIEWS
    monkeypatch.setattr(listing, "_client", lambda: Fake())
    monkeypatch.setattr(score_router.F, "get_feed", lambda bid, network=True: feed(card("rev", "review")))
    listing.invalidate()
    a = FastAPI()
    a.include_router(score_router.router)
    a.include_router(listing.router)
    from kaiku import store
    store.seed()
    return TestClient(a)


def test_score_endpoint_shape(app):
    j = app.get("/api/score/furry-paw").json()
    assert set(j) >= {"score", "label_en", "checks", "pending", "as_of"} and j["score"] == 85 and j["pending"] == ["rev"]
    assert all(set(c) >= {"id", "label_en", "ok", "weight", "detail_en", "source"} for c in j["checks"])
    assert app.get("/api/score/nope").status_code == 404
