"""Dataclasses mirroring the contracts in CLAUDE.md. Core's kaiku/schema.py becomes the single source at merge;
field names are identical so swapping the import is enough."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Union

Hours = list  # [{"start": "09:00", "end": "17:00"}]
CLOSED = "closed"


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
