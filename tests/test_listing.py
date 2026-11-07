"""GET /api/listing: the Yext entity as read through the apply client, normalised, cached 30 s."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku import store
from kaiku.listing import router as listing

from test_score import ENTITY, REVIEWS


class Fake:
    reads = 0

    def get_entity(self, eid):
        Fake.reads += 1
        return ENTITY

    def _req(self, m, p):
        assert (m, p) == ("GET", "/reviews")
        return REVIEWS


@pytest.fixture
def client(monkeypatch):
    Fake.reads = 0
    monkeypatch.setattr(listing, "_client", lambda: Fake())
    listing.invalidate()
    store.seed()
    a = FastAPI()
    a.include_router(listing.router)
    return TestClient(a)


def test_listing_fields(client):
    j = client.get("/api/listing/furry-paw").json()
    assert j["name"] == "Furry Paw Vet Clinic" and j["address"]["text"] == "Tikkurilantie 9, 01300 Vantaa"
    assert j["categories"] == ["E1700"] and j["phone"] == "+358401234567" and j["website"] is None
    assert j["hours_text"]["mon"] == "9-17" and j["hours_text"]["sat"] == "10-14" and j["hours"]["sun"] == "closed"
    assert j["holiday_hours"] == [{"date": "2026-12-24", "hours": [{"start": "09:00", "end": "13:00"}], "text": "9-13"},
                                  {"date": "2026-12-25", "hours": "closed", "text": "closed"}]
    assert j["description"].startswith("A small animal clinic") and j["reviews"] == {"count": 2, "average": 4.0} and j["read_at"]


def test_missing_fields_are_none_not_invented(client, monkeypatch):
    bare = {"name": "X", "meta": {"id": "SinceAI07"}, "hours": {}}
    monkeypatch.setattr(Fake, "get_entity", lambda self, eid: bare)
    monkeypatch.setattr(Fake, "_req", lambda self, m, p: {"count": 0, "averageRating": 0.0})
    j = client.get("/api/listing/furry-paw?fresh=1").json()
    assert j["address"] is None and j["categories"] == [] and j["phone"] is None and j["description"] is None
    assert j["holiday_hours"] == [] and j["hours"]["mon"] is None and j["reviews"] == {"count": 0, "average": None}


def test_cached_30s_and_fresh_bypasses(client):
    client.get("/api/listing/furry-paw"); client.get("/api/listing/furry-paw")
    assert Fake.reads == 1
    client.get("/api/listing/furry-paw?fresh=1")
    assert Fake.reads == 2
    listing.invalidate("furry-paw"); client.get("/api/listing/furry-paw")
    assert Fake.reads == 3


def test_errors(client, monkeypatch):
    assert client.get("/api/listing/nope").status_code == 404
    monkeypatch.setattr(Fake, "get_entity", lambda self, eid: (_ for _ in ()).throw(RuntimeError("boom")))
    assert client.get("/api/listing/furry-paw?fresh=1").status_code == 502
