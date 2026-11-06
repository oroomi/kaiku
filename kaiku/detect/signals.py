"""The five signals Detect collects. Each returns plain dicts (JSON-friendly). Never raises on network trouble."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from kaiku.detect import holidays as hol
from kaiku.suggest.schema import Business, Holiday, valid_hours

ROOT = Path(__file__).resolve().parents[2]
PRIORS = ROOT / "data" / "peer_priors.json"
ENV = Path("/root/hack/kaiku/.env")


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(x)


def holiday_key(name_fi: str) -> str:
    return name_fi.lower().replace("toinen ", "").strip()


# ---- 1. regular hours that weekday ------------------------------------------------------------
def regular_that_day(business: Business, d) -> dict:
    d = _d(d)
    wk = hol.WD_KEYS[d.weekday()]
    hours = business.regular_hours.get(wk) or []
    return {"weekday": wk, "weekday_fi": hol.WD_FI[d.weekday()], "hours": hours, "closed": not hours}


# ---- 2. same holiday last year ------------------------------------------------------------------
def last_year(business: Business, holiday: Holiday) -> dict:
    prev = hol.same_holiday_previous_year(holiday)
    if prev is None:
        return {"found": False}
    for ex in business.last_year_exceptions:
        if ex.get("date") == prev.date:
            if not valid_hours(ex.get("hours")):  # bad data never becomes a proposal
                return {"found": False, "invalid": True, "checked_date": prev.date, "bad_hours": ex.get("hours")}
            same_wd = date.fromisoformat(prev.date).weekday() == date.fromisoformat(holiday.date).weekday()
            return {"found": True, "date": prev.date, "hours": ex["hours"], "weekday_same": same_wd,
                    "matched_holiday": prev.name_fi, "weekday_fi_then": hol.WD_FI[date.fromisoformat(prev.date).weekday()]}
    return {"found": False, "checked_date": prev.date}


# ---- 3. the business's own website --------------------------------------------------------------
_TIME = re.compile(r"(\d{1,2})(?:[.:](\d{2}))?\s*(?:-|–|—|klo)\s*(\d{1,2})(?:[.:](\d{2}))?")


def parse_hours(text: str):
    """'klo 9-13' / 'suljettu' -> [{'start','end'}] | 'closed' | None"""
    t = text.lower()
    m = _TIME.search(t)
    if m:
        a, am, b, bm = m.groups()
        return [{"start": f"{int(a):02d}:{am or '00'}", "end": f"{int(b):02d}:{bm or '00'}"}]
    if "suljettu" in t or "kiinni" in t:
        return "closed"
    return None


def website(business: Business, holiday: Holiday, timeout: float = 5.0) -> dict | None:
    if not business.website:
        return None
    try:
        import httpx
        r = httpx.get(business.website, timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return None
        html = r.text
    except Exception:
        return None
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</(p|li|tr|div|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    key = holiday_key(holiday.name_fi)
    day = f"{_d(holiday.date).day}.{_d(holiday.date).month}."
    for line in text.splitlines():
        low = " ".join(line.split()).lower()
        if not low or (key not in low and day not in low):
            continue
        if any(w in low for w in ("poikkeus", "suljettu", "avoinna", "auki", "klo")):
            hrs = parse_hours(low)
            if hrs is not None and valid_hours(hrs):
                return {"quote": " ".join(line.split()), "hours": hrs, "url": business.website}
    return None


# ---- 4. what Google shows now -------------------------------------------------------------------
def _env_key(name: str) -> str | None:
    try:
        for ln in ENV.read_text().splitlines():
            if ln.startswith(name + "="):
                return ln.split("=", 1)[1].strip().strip('"') or None
    except OSError:
        return None
    return None


def google_now(business: Business, d) -> dict:
    """Serper places lookup. Returns {"status": "unknown"} when no key / no hours (never prints the key)."""
    key = _env_key("SERPER_API_KEY")
    if not key:
        return {"status": "unknown"}
    d = _d(d)
    try:
        import httpx
        r = httpx.post("https://google.serper.dev/places", headers={"X-API-KEY": key},
                       json={"q": f"{business.name} {business.city}".strip(), "gl": "fi", "hl": "fi"}, timeout=8)
        places = r.json().get("places") or []
        oh = (places[0].get("openingHours") or places[0].get("hours")) if places else None
        if isinstance(oh, dict):
            en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][d.weekday()]
            txt = oh.get(en) or oh.get(hol.WD_FI[d.weekday()])
            if txt:
                gh = parse_hours(txt)
                return {"status": "shows_hours", "weekday": en, "text": txt, "hours": gh if valid_hours(gh) else None}
    except Exception:
        pass
    return {"status": "unknown"}


# ---- 5. peer priors -----------------------------------------------------------------------------
def peers(business: Business, holiday: Holiday) -> dict | None:
    data = json.loads(PRIORS.read_text())
    val = (data["priors"].get(business.category) or {}).get(holiday_key(holiday.name_fi))
    if val is None:
        return None
    out = {"category": business.category, "value": val, "label": "hand-made prior"}
    if val == "closed":
        out["hours"] = "closed"
    elif val.startswith("short:"):
        a, b = val[6:].split("-")
        hrs = [{"start": a, "end": b}]
        if not valid_hours(hrs):
            return None
        out["hours"] = hrs
    return out
