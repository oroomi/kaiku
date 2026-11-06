import json
import os
import types
from pathlib import Path

import httpx
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
    assert e["heading"]["value"] == 90 and e["@context"][0] == models.SDM_TRANSPORT


def test_parse_ais_and_ship_entity():
    ships = models.parse_ais(load("aura_ais.json"), {})
    assert len(ships) == 5
    e = models.ship_entity(ships[0], "2026-11-06T19:00:00.000Z")
    assert e["id"].startswith("urn:ngsi-ld:Vehicle:ais:") and e["vehicleType"]["value"] == "vessel"
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


SCHEMA_REQ = {"id", "type", "vehicleType", "category", "location"}
CATEGORY = {"municipalServices", "nonTracked", "private", "public", "specialUsage", "tracked"}


def _sdm_ok(e):
    assert SCHEMA_REQ <= set(e)
    assert set(e["category"]["value"]) <= CATEGORY
    h, sp = e.get("heading", {}).get("value"), e["speed"]["value"]
    assert sp == -1 or sp >= 0
    if "heading" in e:
        assert h == -1 or 0 <= h < 360
    if sp == 0:
        assert h == -1  # stationary vehicle: heading must be -1
    assert e["speed"]["unitCode"] == "KMH"
    ctx = e["@context"]
    assert ctx[0] == models.SDM_TRANSPORT and {"lineRef", "mmsi"} <= set(ctx[1])


def test_sdm_vehicle_conformance_bus_and_ship():
    b = models.parse_foli(load("aura_foli.json"))[0]
    moving, still = models.bus_entity(b, 90.4, "t", 36.0), models.bus_entity(b, 90.4, "t", 0.0)
    _sdm_ok(moving); _sdm_ok(still)
    assert moving["category"]["value"] == ["public", "tracked"] and moving["speed"]["value"] == 36.0 and moving["heading"]["value"] == 90
    assert still["heading"]["value"] == -1
    unk = models.bus_entity(b, None, "t", None)
    assert unk["speed"]["value"] == -1 and "heading" not in unk
    sh = models.parse_ais(load("aura_ais.json"), {})
    for s in sh:
        e = models.ship_entity(s, "t"); _sdm_ok(e)
        assert e["vehicleType"]["value"] == "vessel"
        if s["sog"]:
            assert e["speed"]["value"] == round(s["sog"] * 1.852, 1)
        if s["sog"] == 0:
            assert e["heading"]["value"] == -1
    assert models.compact(models.ship_entity(sh[0], "t"))["kind"] == "ship"
    assert models.subscription_body({"id": "a", "entity_type": "ship", "geo_center": [22, 60], "geo_radius_m": 500}, "u")["q"] == 'vehicleType=="vessel"'


def _langs(fi_en_pairs, tool_in):
    """Fake client whose tool call returns given (fi, en) and whose translate call answers by target language."""
    def create(**kw):
        if kw.get("tools"):
            ti = {**tool_in, "description_fi": fi_en_pairs[0], "description_en": fi_en_pairs[1]}
            return types.SimpleNamespace(stop_reason="tool_use", content=[types.SimpleNamespace(type="tool_use", name="propose_subscription", input=ti)])
        to_fi = "Finnish" in kw["system"]
        out = "Ilmoita, kun bussi on alle 300 m Kauppatorista." if to_fi else "Tell me when a bus is within 300 m of Kauppatori."
        return types.SimpleNamespace(stop_reason="end_turn", content=[types.SimpleNamespace(type="text", text=out)])
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def test_explanations_always_fi_and_en():
    en_only = "Tell me when a bus is within 300 m of Kauppatori."
    fi_only = "Ilmoita kun bussi on alle 300 m Kauppatorista."
    r = agent.ask("tell me when a bus is within 300 m of Kauppatori", client=_langs((en_only, en_only), TOOL_IN))  # fi field in English
    assert agent.lang_of(r["explanation_fi"]) == "fi" and agent.lang_of(r["explanation_en"]) == "en"
    r = agent.ask("kerro kun bussi", client=_langs((fi_only, fi_only), TOOL_IN))  # en field in Finnish
    assert agent.lang_of(r["explanation_fi"]) == "fi" and agent.lang_of(r["explanation_en"]) == "en"
    assert subs.get_proposal(r["proposal"]["id"])["description_en"] == r["explanation_en"]
    r = agent.ask("x", client=_langs((fi_only, en_only), TOOL_IN))  # swapped
    assert r["explanation_fi"] == fi_only or agent.lang_of(r["explanation_fi"]) == "fi"


def test_explanation_template_when_translation_fails():
    c = _langs(("Tell me when a bus is near.", "Tell me when a bus is near."), TOOL_IN)
    orig = c.messages.create
    def create(**kw):
        if kw.get("tools"):
            return orig(**kw)
        raise RuntimeError("down")
    c.messages.create = create
    r = agent.ask("x", client=c)
    assert r["explanation_fi"].startswith("Ilmoitan") and "300 m" in r["explanation_fi"] and agent.lang_of(r["explanation_en"]) == "en"


def test_text_only_answer_gets_both_languages():
    r = agent.ask("moi", client=_fake(text="Voin auttaa vain bussi- ja laivatilauksissa."))
    assert agent.lang_of(r["explanation_fi"]) == "fi" and agent.lang_of(r["explanation_en"]) == "en"


def test_judge_endpoint_has_link_header_curl(monkeypatch):
    class Boom:
        def __init__(self, *a, **k): raise httpx.ConnectError("x")
    monkeypatch.setattr(aura_router.httpx, "AsyncClient", Boom)
    j = _app().get("/api/aura/judge").json()
    assert "Link: <" + models.SDM_TRANSPORT in j["curl"] and "Accept: application/ld+json" in j["curl"] and j["entity"] is None
