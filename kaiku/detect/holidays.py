"""Finnish holidays from Nager.Date (live), cached in data/holidays_fi_2026.json, plus flag days that are not
public holidays (isänpäivä, äitienpäivä, uudenvuodenaatto), marked public_holiday=false."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from kaiku.suggest.schema import Holiday

CACHE = Path(__file__).resolve().parents[2] / "data" / "holidays_fi_2026.json"
API = "https://date.nager.at/api/v3/PublicHolidays/{year}/FI"
WD_FI = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
WD_FI_SHORT = ["ma", "ti", "ke", "to", "pe", "la", "su"]
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


def fetch_year(year: int) -> list[dict]:
    import httpx
    r = httpx.get(API.format(year=year), timeout=15)
    r.raise_for_status()
    out = []
    for h in r.json():
        d = date.fromisoformat(h["date"])
        out.append({"date": h["date"], "name_fi": h["localName"], "name_en": h["name"], "public_holiday": True,
                    "weekday": WD_FI[d.weekday()]})
    return out


def build_cache(years=(2025, 2026, 2027), path: Path = CACHE) -> list[dict]:
    items = []
    for y in years:
        items += fetch_year(y) + flag_days(y)
    # keep 2027 only up to Loppiainen 6.1.2027
    items = [h for h in items if h["date"] <= "2027-01-06" or not h["date"].startswith("2027")]
    items.sort(key=lambda h: h["date"])
    path.write_text(json.dumps({"source": "https://date.nager.at/api/v3/PublicHolidays/{year}/FI + computed flag days",
                                "holidays": items}, ensure_ascii=False, indent=1))
    return items


_cache: list[Holiday] | None = None


def all_holidays() -> list[Holiday]:
    global _cache
    if _cache is None:
        if not CACHE.exists():
            build_cache()
        data = json.loads(CACHE.read_text())["holidays"]
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
