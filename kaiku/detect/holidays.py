"""Finnish holidays: bundled data/holidays_fi_2026.json first, refreshed from Nager.Date when missing or older than
30 days (failures keep the bundled file), plus flag days that are not
public holidays (isänpäivä, äitienpäivä, uudenvuodenaatto), marked public_holiday=false."""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

from kaiku.suggest.schema import Holiday

CACHE = Path(__file__).resolve().parents[2] / "data" / "holidays_fi_2026.json"
API = "https://date.nager.at/api/v3/PublicHolidays/{year}/FI"
WD_FI = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
WD_FI_SHORT = ["ma", "ti", "ke", "to", "pe", "la", "su"]
WD_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# English names for the holidays Nager gives only the Finnish local name for
NAME_EN = {"Uudenvuodenaatto": "New Year's Eve", "Isänpäivä": "Father's Day", "Äitienpäivä": "Mother's Day"}
# Nager spells some names differently from what a Finn writes
FI_NORMALISE = {"Pääsiäispäivä": "Pääsiäispäivä"}


def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def flag_days(year: int) -> list[dict]:
    out = []
    for d, fi in ((_nth_sunday(year, 5, 2), "Äitienpäivä"), (_nth_sunday(year, 11, 2), "Isänpäivä"),
                  (date(year, 12, 31), "Uudenvuodenaatto")):
        out.append({"date": d.isoformat(), "name_fi": fi, "name_en": NAME_EN[fi], "public_holiday": False,
                    "weekday": WD_FI[d.weekday()]})
    return out


def fetch_year(year: int, timeout: float = 5.0) -> list[dict]:
    import httpx
    r = httpx.get(API.format(year=year), timeout=timeout)
    r.raise_for_status()
    out = []
    for h in r.json():
        d = date.fromisoformat(h["date"])
        out.append({"date": h["date"], "name_fi": h["localName"], "name_en": h["name"], "public_holiday": True,
                    "weekday": WD_FI[d.weekday()]})
    return out


def build_cache(years=(2025, 2026, 2027), path: Path = CACHE, timeout: float = 5.0) -> list[dict]:
    """Fetch from Nager.Date and rewrite the cache atomically. Raises on any failure (callers catch)."""
    items = []
    for y in years:
        items += fetch_year(y, timeout) + flag_days(y)
    # keep 2027 only up to Loppiainen 6.1.2027
    items = [h for h in items if h["date"] <= "2027-01-06" or not h["date"].startswith("2027")]
    items.sort(key=lambda h: h["date"])
    if len(items) < 20:
        raise ValueError("Nager.Date returned too few holidays")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"source": "https://date.nager.at/api/v3/PublicHolidays/{year}/FI + computed flag days",
                               "holidays": items}, ensure_ascii=False, indent=1))
    tmp.replace(path)
    return items


_cache: list[Holiday] | None = None


MAX_AGE_DAYS = 30


def _stale() -> bool:
    try:
        return time.time() - CACHE.stat().st_mtime > MAX_AGE_DAYS * 86400
    except OSError:
        return True  # missing


def _load_bundled() -> list[dict] | None:
    try:
        return json.loads(CACHE.read_text())["holidays"]
    except Exception:
        return None


def all_holidays() -> list[Holiday]:
    """Bundled file first. If it is missing or older than 30 days, try Nager.Date (5 s timeout) and rewrite it;
    on any failure keep the bundled file. Never raises."""
    global _cache
    if _cache is None:
        data = _load_bundled()
        if data is None or _stale():
            try:
                data = build_cache()
            except Exception:
                data = _load_bundled()  # keep what we have (may be None)
        if data is None:  # no file, no network: the computed flag days are still true
            data = [h for y in (2025, 2026, 2027) for h in flag_days(y)]
        _cache = [Holiday(**h) for h in data]
    return _cache


def get(d) -> Holiday | None:
    iso = d if isinstance(d, str) else d.isoformat()
    return next((h for h in all_holidays() if h.date == iso), None)


def upcoming(today, days: int = 21) -> list[Holiday]:
    t = today if isinstance(today, date) else date.fromisoformat(today)
    end = t + timedelta(days=days)
    return [h for h in all_holidays() if t <= date.fromisoformat(h.date) <= end]


def same_holiday_previous_year(h: Holiday) -> Holiday | None:
    """The same holiday one year earlier, matched by name (works for moveable ones like Pääsiäinen)."""
    y = int(h.date[:4]) - 1
    return next((x for x in all_holidays() if x.name_fi == h.name_fi and x.date.startswith(str(y))), None)


if __name__ == "__main__":
    print(len(build_cache()), "holidays cached to", CACHE)
