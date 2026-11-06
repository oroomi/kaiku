"""Aura agent: turns a sentence into ONE proposed NGSI-LD subscription. It can only propose; a human taps to create."""
from __future__ import annotations

import os

from . import subs

MODEL = "claude-sonnet-5-5"

PLACES = {
    "Kauppatori": (22.2666, 60.4518), "Turun tuomiokirkko": (22.2783, 60.4524), "Turun satama": (22.2200, 60.4357),
    "Turun linna": (22.2289, 60.4352), "Kupittaa": (22.2960, 60.4500),
}

SYSTEM = """You are Aura, the assistant of a live Turku map backed by an NGSI-LD context broker (Orion-LD).
The broker holds live Vehicle entities: buses (vehicleType "bus", Föli) and ships (vehicleType "ship", AIS), plus weather.
You CAN ONLY PROPOSE. You never create anything: you call propose_subscription once and a human approves it with one tap.
Known places (longitude, latitude):
{places}
Rules: pick the place the person means; if they give no distance use 300 m for buses and 2000 m for ships. entity_type is "bus"
or "ship". If the request is not a geofence subscription on buses or ships (or the place is unknown), do not call the tool and
answer in one short sentence in the person's language, saying what you can do. description_fi is correct Finnish, no em or
en dashes. place_label_fi is the place in elative form ("Kauppatorista", "Turun satamasta"). Answer in the person's language only
through the tool fields."""

TOOL = {
    "name": "propose_subscription",
    "description": "Propose an NGSI-LD geofence subscription. A human must approve before it exists.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "enum": ["bus", "ship"], "description": "Vehicle kind (NGSI-LD type Vehicle, vehicleType)"},
            "geo_center": {"type": "array", "items": {"type": "number"}, "description": "[longitude, latitude]"},
            "geo_radius_m": {"type": "integer", "minimum": 20, "maximum": 30000},
            "attribute_condition": {"type": "string", "description": "optional NGSI-LD q filter, e.g. lineRef==\"2\""},
            "place_label_fi": {"type": "string"},
            "place_label_en": {"type": "string", "description": "place name in English, e.g. Kauppatori, the port of Turku"},
            "description_fi": {"type": "string"},
            "description_en": {"type": "string"},
        },
        "required": ["entity_type", "geo_center", "geo_radius_m", "place_label_fi", "place_label_en", "description_fi", "description_en"],
        "additionalProperties": False,
    },
}


def make_client():
    import anthropic
    return anthropic.Anthropic()


def ask(text: str, client=None) -> dict:
    """Returns {proposal|None, explanation_fi, explanation_en}."""
    client = client or make_client()
    places = "\n".join(f"- {n}: {lon}, {lat}" for n, (lon, lat) in PLACES.items())
    kw = dict(model=MODEL, max_tokens=1500, system=SYSTEM.format(places=places), tools=[TOOL],
              tool_choice={"type": "auto"}, output_config={"effort": "low"},
              messages=[{"role": "user", "content": text[:600]}])
    resp = client.messages.create(**kw)
    if resp.stop_reason == "refusal":
        return {"proposal": None, "explanation_fi": "En voi ehdottaa tätä tilausta.", "explanation_en": "I cannot propose that subscription."}
    for b in resp.content:
        if b.type == "tool_use" and b.name == "propose_subscription":
            a = dict(b.input)
            lon, lat = a["geo_center"]
            if not (19 < lon < 25 and 59 < lat < 62):
                break
            a["attribute_condition"] = (a.get("attribute_condition") or "").strip() or None
            p = subs.new_proposal(a)
            return {"proposal": p, "explanation_fi": a["description_fi"], "explanation_en": a["description_en"]}
    said = " ".join(b.text for b in resp.content if b.type == "text").strip()
    return {"proposal": None, "explanation_fi": said or "Voin ehdottaa tilauksen busseista tai laivoista Turun paikkojen lähellä.",
            "explanation_en": "I can propose a subscription on buses or ships near Turku places." if not said else said}
