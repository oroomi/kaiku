"""THE clock for the chain. Fake date persisted in data/timetravel.json so all processes agree.
EN: today() returns the fake date if set, else the real Helsinki date."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from ._paths import data_dir, read_json, write_json_atomic

TZ = ZoneInfo("Europe/Helsinki")


def _file():
    return data_dir() / "timetravel.json"


def fake_date() -> Optional[date]:
    raw = read_json(_file(), {}).get("today")
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def is_fake() -> bool:
    return fake_date() is not None


def today() -> date:
    return fake_date() or datetime.now(TZ).date()


def now() -> datetime:
    """Aware datetime consistent with today(): real time of day on the (maybe fake) date."""
    real = datetime.now(TZ)
    f = fake_date()
    if f is None:
        return real
    return datetime.combine(f, real.time().replace(tzinfo=None), tzinfo=TZ)


def set_today(d: Optional[date]) -> None:
    if d is None:
        clear()
        return
    write_json_atomic(_file(), {"today": d.isoformat()})


def clear() -> None:
    try:
        _file().unlink()
    except FileNotFoundError:
        pass
