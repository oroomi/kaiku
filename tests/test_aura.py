import json
import os
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.aura import agent, models, router as aura_router, subs

FX = Path(__file__).parent / "fixtures"
load = lambda n: json.loads((FX / n).read_text())  # noqa: E731


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(subs, "STORE", tmp_path / "subs.json")
    aura_router._recent.clear()


def test_parse_foli_and_bus_entity():
    buses = models.parse_foli(load("aura_foli.json"))
    assert len(buses) == 6 and buses[0]["lat"] and buses[0]["ref"]
    e = models.bus_entity(buses[0], 90.0, "2026-11-06T19:00:00.000Z")
    assert e["id"].startswith("urn:ngsi-ld:Vehicle:foli:") and e["type"] == "Vehicle"
    assert e["location"]["type"] == "GeoProperty" and e["location"]["value"]["type"] == "Point"
    assert e["vehicleType"]["value"] == "bus" and "CC BY 4.0" in e["source"]["value"] and e["source"]["observedAt"]
    assert e["heading"]["value"] == 90 and "@context" not in e


def test_parse_ais_and_ship_entity():
    ships = models.parse_ais(load("aura_ais.json"), {})
    assert len(ships) == 5
    e = models.ship_entity(ships[0], "2026-11-06T19:00:00.000Z")
    assert e["id"].startswith("urn:ngsi-ld:Vehicle:ais:") and e["vehicleType"]["value"] == "ship"
    assert e["location"]["value"]["coordinates"][0] > 20


def test_weather_entity():
    w = models.parse_weather(load("aura_weather.json"))
    e = models.weather_entity(w)
    assert e["id"] == "urn:ngsi-ld:WeatherObserved:turku" and e["type"] == "WeatherObserved"
    assert {"temperature", "windSpeed", "precipitation", "weatherType", "location", "dateObserved", "source"} <= set(e)


def test_compact_roundtrip_tolerates_expanded_names():
    e = models.bus_entity(models.parse_foli(load("aura_foli.json"))[0], 10, models.iso())
    c = models.compact(e)
    assert c["kind"] == "bus" and c["lon"] and models.age_s(c["obs"]) < 5
    e2 = {"id": e["id"], "type": "Vehicle", "https://x.org/ns/location": e["location"], "https://x.org/ns/vehicleType": e["vehicleType"]}
    assert models.compact(e2)["lat"] == c["lat"]


def test_subscription_shape():
    p = {"id": "abc", "entity_type": "bus", "geo_center": [22.2666, 60.4518], "geo_radius_m": 300, "description_en": "x"}
    b = models.subscription_body(p, "http://127.0.0.1:8210/aura/notify")
    assert b["type"] == "Subscription" and b["watchedAttributes"] == ["location"]
    assert b["geoQ"] == {"geometry": "Point", "coordinates": [22.2666, 60.4518], "georel": "near;maxDistance==300"}
    assert b["notification"]["endpoint"]["uri"].endswith("/aura/notify") and b["q"] == 'vehicleType=="bus"'


def _fake(tool_input=None, text="Voin auttaa vain bussi- ja laivatilauksissa."):
    def create(**kw):
        assert kw["model"] == "claude-sonnet-5-5" and kw["tool_choice"] == {"type": "auto"} and "thinking" not in kw
        blocks = [types.SimpleNamespace(type="tool_use", name="propose_subscription", input=tool_input)] if tool_input else [types.SimpleNamespace(type="text", text=text)]
        return types.SimpleNamespace(stop_reason="tool_use" if tool_input else "end_turn", content=blocks)
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


TOOL_IN = {"entity_type": "bus", "geo_center": [22.2666, 60.4518], "geo_radius_m": 300, "place_label_fi": "Kauppatorista", "place_label_en": "Kauppatori",
           "description_fi": "Ilmoita kun bussi on alle 300 m Kauppatorista.", "description_en": "Tell me when a bus is within 300 m of Kauppatori."}


def test_agent_proposes_and_stores_pending():
    r = agent.ask("tell me when a bus is within 300 m of Kauppatori", client=_fake(TOOL_IN))
    assert r["proposal"]["status"] == "pending" and r["explanation_en"] and subs.get_proposal(r["proposal"]["id"])["geo_radius_m"] == 300


def test_agent_no_tool_returns_text_only():
    assert agent.ask("moi", client=_fake())["proposal"] is None


def _app():
    app = FastAPI()
    app.include_router(aura_router.router)
    return TestClient(app)


def test_ask_endpoint_with_fake_client(monkeypatch):
    monkeypatch.setattr(agent, "make_client", lambda: _fake(TOOL_IN))
    r = _app().post("/api/aura/ask", json={"text": "bus near Kauppatori"})
    assert r.status_code == 200 and r.json()["proposal"]["entity_type"] == "bus"


def test_notify_returns_204_and_queues(monkeypatch):
    p = subs.new_proposal({**TOOL_IN})
    d = subs._load(); d["active"]["urn:ngsi-ld:Subscription:aura-x"] = p; subs._save(d)
    emitted = []
    import kaiku.events as ev
    monkeypatch.setattr(ev, "emit", lambda e: emitted.append(e))
    bus = models.bus_entity(models.parse_foli(load("aura_foli.json"))[0], 0, models.iso())
    bus["location"]["value"]["coordinates"] = [22.2666, 60.4530]
    r = _app().post("/aura/notify", json={"id": "n1", "type": "Notification", "subscriptionId": "urn:ngsi-ld:Subscription:aura-x", "data": [bus]})
    assert r.status_code == 204
    assert aura_router._recent and "Tilaus laukesi" in aura_router._recent[-1]["title_fi"] and "Kauppatorista" in aura_router._recent[-1]["title_fi"]
    assert emitted and emitted[0].step == "broker" and "Subscription fired" in emitted[0].title_en


@pytest.mark.skipif(os.environ.get("KAIKU_LIVE") != "1", reason="live broker")
def test_live_entities_from_broker():
    r = _app().get("/api/aura/entities?type=Vehicle")
    assert r.status_code == 200 and r.json()["source"] in ("broker", "fallback cache")
