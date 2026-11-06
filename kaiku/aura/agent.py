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
The broker holds live Vehicle entities: buses (vehicleType "bus", Föli) and ships (vehicleType "vessel", AIS; the tool calls it "ship"), plus weather.
You CAN ONLY PROPOSE. You never create anything: you call propose_subscription once and a human approves it with one tap.
Known places (longitude, latitude):
{places}
Rules: pick the place the person means; if they give no distance use 300 m for buses and 2000 m for ships. entity_type is "bus"
or "ship". If the request is not a geofence subscription on buses or ships (or the place is unknown), do not call the tool and
answer in one short sentence in the person's language, saying what you can do. description_fi is correct Finnish, no em or
en dashes. place_label_fi is the place in elative form ("Kauppatorista", "Turun satamasta"). ALWAYS fill BOTH languages whatever
language the person writes in: description_fi and the Finnish text are Finnish, description_en and the English text are English.
Never put English in a _fi field or Finnish in an _en field. If you answer in plain text instead of the tool, write one short
sentence in the person's language."""

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


_FI = set("ja on ei että kun voin tilaus tilauksen bussi bussin linja laiva laivan alle tai sinulle lähellä kerro jos ilmoita saapuu kohteesta oli ovat sekä mutta mitä miten voit tämä satamasta kauppatorista".split())
_EN = set("the and is when a an within of tell you can i to near bus ship for will that this it are be notify me from at".split())


def lang_of(t: str) -> str | None:
    """Cheap fi/en detector for one sentence: stopword counts plus ä/ö. None when unclear."""
    w = [x.strip(".,;:!?\"'()").lower() for x in t.split()]
    fi = sum(x in _FI for x in w) + 2 * sum(c in "äö" for c in t.lower())
    en = sum(x in _EN for x in w)
    return "fi" if fi > en else "en" if en > fi else None


def template_pair(a: dict) -> tuple[str, str]:
    r = int(a["geo_radius_m"])
    fi = f"Ilmoitan, kun {'laiva' if a.get('entity_type') == 'ship' else 'bussi'} on alle {r} m {a.get('place_label_fi') or 'kohteesta'}."
    en = f"I will tell you when a {'ship' if a.get('entity_type') == 'ship' else 'bus'} is within {r} m of {a.get('place_label_en') or 'the place'}."
    return fi, en


def _translate(text: str, to: str, client) -> str | None:
    try:
        r = client.messages.create(model=MODEL, max_tokens=300, output_config={"effort": "low"},
                                   system=f"Translate to {'Finnish' if to == 'fi' else 'English'}. Output only the translation. "
                                          "No em or en dashes.", messages=[{"role": "user", "content": text}])
        out = " ".join(b.text for b in r.content if b.type == "text").strip()
        return out if out and lang_of(out) in (to, None) else None
    except Exception:  # noqa: BLE001  fall back to the template
        return None


def fix_pair(fi: str, en: str, client, fallback: tuple[str, str]) -> tuple[str, str]:
    """Make sure fi is Finnish and en is English: swap if reversed, copy-translate if both are one language, else template."""
    fi, en = (fi or "").strip(), (en or "").strip()
    lf, le = lang_of(fi) if fi else None, lang_of(en) if en else None
    if lf == "en" and le == "fi":
        return en, fi
    if fi and lf == "en":      # fi field holds English
        fi = _translate(fi, "fi", client) or fallback[0]
    if en and le == "fi":      # en field holds Finnish
        en = _translate(en, "en", client) or fallback[1]
    if not fi:
        fi = _translate(en, "fi", client) or fallback[0]
    if not en:
        en = _translate(fi, "en", client) or fallback[1]
    return fi, en


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
            fi, en = fix_pair(a.get("description_fi"), a.get("description_en"), client, template_pair(a))
            a["description_fi"], a["description_en"] = fi, en
            p = subs.new_proposal(a)
            return {"proposal": p, "explanation_fi": fi, "explanation_en": en}
    said = " ".join(b.text for b in resp.content if b.type == "text").strip()
    dflt = ("Voin ehdottaa tilauksen busseista tai laivoista Turun paikkojen lähellä.",
            "I can propose a subscription on buses or ships near Turku places.")
    if not said:
        fi, en = dflt
    else:
        lg = lang_of(said) or "en"
        other = _translate(said, "en" if lg == "fi" else "fi", client) or dflt[1 if lg == "fi" else 0]
        fi, en = (said, other) if lg == "fi" else (other, said)
    return {"proposal": None, "explanation_fi": fi, "explanation_en": en}
