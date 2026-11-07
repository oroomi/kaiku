"""Per-business preferences learned from decisions (edit / decline / standing permission).
Stored in data/learn_prefs.json (atomic writes). Every Finnish string has an English gloss next to it."""
from __future__ import annotations

import copy
import re
import threading
from datetime import date

from ._paths import data_dir, read_json, write_json_atomic
from . import timetravel

_lock = threading.Lock()

DECLINE_SUPPRESS_FI = "Olet hylännyt tämän ehdotuksen kahdesti"  # EN: You have declined this suggestion twice
DECLINE_SUPPRESS_EN = "You have declined this suggestion twice"
DECLINE_PENALTY = 0.15
EDIT_CONF = 0.9
WD = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _file():
    return data_dir() / "learn_prefs.json"


def _slug(name: str) -> str:
    s = (name or "").lower().translate(str.maketrans("äöå", "aoa"))
    return re.sub(r"[^a-z0-9]+", "", s)


def holiday_id(suggestion: dict) -> str:
    """jouluaatto etc. from suggestion['holiday_id'|'holiday'.name_fi|'holiday_name_fi']; fallback 'md-12-24'."""
    if suggestion.get("holiday_id"):
        return _slug(suggestion["holiday_id"])
    h = suggestion.get("holiday") or {}
    name = h.get("id") or h.get("name_fi") or suggestion.get("holiday_name_fi")
    if name:
        return _slug(name)
    d = suggestion.get("holiday_date") or ""
    return "md-" + d[5:] if len(d) >= 10 else "unknown"


def weekday_of(suggestion: dict) -> str:
    try:
        return WD[date.fromisoformat(suggestion["holiday_date"]).weekday()]
    except (KeyError, ValueError, TypeError):
        return ""


def _hours_fi(h) -> str:
    """[{start:'10:00',end:'14:00'}] -> '10-14'; EN: hours as 10-14."""
    if h == "closed" or not h:
        return "kiinni"

    def t(x):
        hh, mm = x.split(":")
        return str(int(hh)) + ("" if mm == "00" else "." + mm)
    return ", ".join(f"{t(s['start'])}-{t(s['end'])}" for s in h)


def _hours_en(h) -> str:
    return "closed" if h == "closed" or not h else _hours_fi(h)


def load() -> dict:
    return read_json(_file(), {})


def get_prefs(business_id: str) -> dict:
    return load().get(business_id, {"edits": {}, "edits_by_weekday": {}, "declines": {}, "standing_permission": None})


CHANNELS = ("email", "whatsapp", "call")
_CH_NAME_EN = {"email": "email", "whatsapp": "WhatsApp", "call": "a call"}
_CH_NAME_FI = {"email": "sähköposti", "whatsapp": "WhatsApp", "call": "puhelu"}
_CH_WORDS = {"email": ("email", "e-mail", "mail", "sähköposti", "sahkoposti", "sähköpostilla", "sahkopostilla", "mailiin"),
             "whatsapp": ("whatsapp", "whats app", "whatsap", "wa", "whatsappilla", "whatsappiin"),
             "call": ("call", "phone", "ring", "call me", "phone call", "a call", "by call", "by phone", "soita", "puhelu",
                      "puhelimella", "soitto", "soittaa")}


def parse_channel(text: str) -> str | None:
    """'email' | 'whatsapp' | 'call' from the owner's own words, None for anything else (sms is none of the three)."""
    t = re.sub(r"[^\w\s-]", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:by|via|through|on|please|just|use|with|prefer|i prefer|i d prefer|id prefer|i would prefer|" r"i want|i d like|id like)\s+", "", t)
    t = re.sub(r"^(?:by|via|through|on|please|just|use|with)\s+", "", t)
    if not t or len(t.split()) > 5:
        return None
    hits = {ch for ch, ws in _CH_WORDS.items() for w in ws if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t)}
    return next(iter(hits)) if len(hits) == 1 else None


def get_contact_channel(business_id: str) -> str | None:
    """How the owner wants to be reached first next time: 'email' | 'whatsapp' | 'call' | None (never asked / not answered)."""
    v = load().get(business_id or "", {}).get("contact_channel")
    return v if v in CHANNELS else None


def set_contact_channel(business_id: str, channel: str, said: str = "") -> dict:
    """Store the owner's preferred first channel (persisted with the other prefs, wiped by the same reset) and emit the
    learn event. The detail carries the owner's own words."""
    if channel not in CHANNELS:
        raise ValueError("channel must be one of " + ", ".join(CHANNELS))
    with _lock:
        allp = load()
        p = allp.setdefault(business_id, {"edits": {}, "edits_by_weekday": {}, "declines": {}, "standing_permission": None})
        p["contact_channel"] = channel
        write_json_atomic(_file(), allp)
    _emit(business_id, {}, f"Opittu: haluaa jatkossa yhteydenoton: {_CH_NAME_FI[channel]}",
          f"Learned: prefers {_CH_NAME_EN[channel] if channel != 'call' else 'a call'} next time",
          {"channel": channel, "said": (said or "")[:200]})
    return {"contact_channel": channel}


def _emit(business_id, suggestion, fi, en, detail):
    try:
        from kaiku import events  # type: ignore
        from kaiku.schema import Event  # type: ignore
        events.emit(Event(step="learn", business_id=business_id, suggestion_id=suggestion.get("id", ""),
                          title_fi=fi, title_en=en, detail=detail))
    except Exception:
        pass  # core not importable or store unavailable: learning still works


def record_decision(business_id: str, suggestion: dict, decision: dict) -> dict:
    hid, wd = holiday_id(suggestion), weekday_of(suggestion)
    action = decision.get("action")
    today = timetravel.today().isoformat()
    learned_fi = learned_en = None
    with _lock:
        allp = load()
        p = allp.setdefault(business_id, {"edits": {}, "edits_by_weekday": {}, "declines": {}, "standing_permission": None})
        if action == "edit" and decision.get("edited") is not None:
            rec = {"hours": decision["edited"], "at": today}
            p["edits"][hid] = rec
            if wd:
                p["edits_by_weekday"][f"{hid}|{wd}"] = rec
            p["declines"].pop(hid, None)  # an edit means they engage with it again
            learned_fi = f"Opittu: {hid} aukeaa jatkossa {_hours_fi(decision['edited'])}"
            learned_en = f"Learned: {hid} will use {_hours_en(decision['edited'])} next time"
        elif action == "decline":
            d = p["declines"].setdefault(hid, {"count": 0, "reasons": []})
            d["count"] += 1
            if decision.get("reason_chip"):
                d["reasons"].append(decision["reason_chip"])
            d["last_at"] = today
            learned_fi = f"Opittu: ehdotus {hid} hylättiin ({d['count']}. kerta)"
            learned_en = f"Learned: suggestion for {hid} declined (time {d['count']})"
        if decision.get("standing_permission") and action in ("approve", "edit"):
            scope = "all" if decision.get("scope") == "all" else "holiday"
            p["standing_permission"] = {"scope": scope, "holiday": hid, "granted_at": today}
            learned_fi = (learned_fi or "") + "; pysyvä lupa annettu"
            learned_en = (learned_en or "") + "; standing permission granted"
        write_json_atomic(_file(), allp)
        out = copy.deepcopy(p)
    if learned_fi:
        _emit(business_id, suggestion, learned_fi.lstrip("; "), learned_en.lstrip("; "), {"holiday": hid, "action": action})
    return out


def apply_prefs(business_id: str, suggestion: dict) -> dict:
    """Return a NEW suggestion dict adjusted by what we learned. Input is never mutated."""
    s = copy.deepcopy(suggestion)
    p = get_prefs(business_id)
    hid, wd = holiday_id(s), weekday_of(s)
    notes = []

    dec = p["declines"].get(hid)
    if dec and dec["count"] >= 2:
        s.update(kind="no_change", proposed=None)
        s["reason_fi"] = DECLINE_SUPPRESS_FI
        s["reason_en"] = DECLINE_SUPPRESS_EN
        s["suppressed"] = True
        return s

    edit = p["edits_by_weekday"].get(f"{hid}|{wd}") or p["edits"].get(hid)
    if edit:
        hrs = edit["hours"]
        s["kind"] = "closed" if hrs == "closed" else "hours"
        s["proposed"] = None if hrs == "closed" else hrs
        s["confidence"] = max(float(s.get("confidence", 0)), EDIT_CONF)
        s["reason_fi"] = _join(s.get("reason_fi"), f"Viime vuonna muokkasit tämän ajaksi {_hours_fi(hrs)}")
        s["reason_en"] = _join(s.get("reason_en"), f"Last year you edited this to {_hours_en(hrs)}")
        s["learned_from_edit"] = True
    elif dec and dec["count"] == 1:
        s["confidence"] = round(max(0.0, float(s.get("confidence", 0)) - DECLINE_PENALTY), 4)
        s["reason_fi"] = _join(s.get("reason_fi"), "Hylkäsit tämän ehdotuksen aiemmin")
        s["reason_en"] = _join(s.get("reason_en"), "You declined this suggestion before")

    sp = p.get("standing_permission")
    if sp and s.get("kind") in ("hours", "closed") and (sp["scope"] == "all" or sp.get("holiday") == hid):
        s["auto_apply"] = True
        s["auto_apply_reason_fi"] = (f"Annoit pysyvän luvan ({_fi_d(sp['granted_at'])}), joten päivitämme tämän puolestasi"
                                    if sp["scope"] == "all" else
                                    f"Annoit pysyvän luvan tälle pyhälle ({_fi_d(sp['granted_at'])}), joten päivitämme sen puolestasi")
        s["auto_apply_reason_en"] = "You gave standing permission, so we update this for you"
    return s


def _fi_d(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d.day}.{d.month}.{d.year}"
    except ValueError:
        return iso


def _join(a, b):
    return f"{a}. {b}" if a else b
