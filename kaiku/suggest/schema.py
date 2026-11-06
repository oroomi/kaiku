"""Dataclasses mirroring the contracts in CLAUDE.md. Core's kaiku/schema.py becomes the single source at merge;
field names are identical so swapping the import is enough."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Union

Hours = list  # [{"start": "09:00", "end": "17:00"}]
CLOSED = "closed"
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def valid_interval(x) -> bool:
    """{"start": "HH:MM", "end": "HH:MM"} with start strictly before end."""
    if not isinstance(x, dict):
        return False
    s, e = x.get("start"), x.get("end")
    return (isinstance(s, str) and isinstance(e, str) and bool(_HHMM.match(s)) and bool(_HHMM.match(e)) and s < e)


def valid_hours(h) -> bool:
    """"closed" or a non-empty list of valid, non-overlapping intervals."""
    if h == CLOSED:
        return True
    if not isinstance(h, list) or not h or not all(valid_interval(x) for x in h):
        return False
    srt = sorted(h, key=lambda x: x["start"])
    return all(a["end"] <= b["start"] for a, b in zip(srt, srt[1:]))


@dataclass
class Business:
    id: str
    name: str
    category: str = "shop"
    address: str = ""
    city: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    regular_hours: dict = field(default_factory=dict)
    last_year_exceptions: list = field(default_factory=list)
    website: Optional[str] = None
    owner_whatsapp: Optional[str] = None
    source: str = "sample"
    exceptions: list = field(default_factory=list)  # extra: exception hours already set for the coming year, same shape as last_year_exceptions

    @classmethod
    def from_dict(cls, d: dict) -> "Business":
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Holiday:
    date: str
    name_fi: str
    name_en: str
    public_holiday: bool
    weekday: str

    def to_dict(self):
        return asdict(self)


@dataclass
class Detection:
    business_id: str
    holiday_date: str
    signals: dict = field(default_factory=dict)
    reason_codes: list = field(default_factory=list)
    holiday: Optional[dict] = None  # extra, convenience for suggest
    status: str = "ok"  # extra: "ok" | "past" (the date is before today: nothing to suggest)

    def to_dict(self):
        return asdict(self)


@dataclass
class Suggestion:
    id: str
    business_id: str
    holiday_date: str
    kind: str  # hours|closed|no_change|ask
    proposed: Optional[list]
    confidence: float
    reasons: list = field(default_factory=list)  # {source, dataset_id, text_fi, text_en}
    message_fi: str = ""
    message_en: str = ""
    status: str = "proposed"
    channel_log: list = field(default_factory=list)
    question_fi: Optional[str] = None  # extra, only for kind=ask
    # extras read by the contact lane
    business_name: str = ""
    holiday_name_fi: Optional[str] = None
    holiday_name_en: Optional[str] = None
    last_year_hours: Any = None  # [{start,end}] | "closed" | None
    google_now: dict = field(default_factory=lambda: {"status": "unknown"})
    decide_url: Optional[str] = None  # core fills it

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
