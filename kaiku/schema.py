"""Data contracts. Owned by core; every other module imports these, never redefines."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class Span(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"


Hours = list[Span]  # [] means closed that day


class Exception_(BaseModel):
    date: str  # "2025-12-24"
    hours: Union[list[Span], Literal["closed"]]


class Business(BaseModel):
    id: str
    name: str
    address: str
    city: str = ""
    lat: float
    lon: float
    category: str
    regular_hours: dict[str, list[Span]]  # keys mon..sun
    last_year_exceptions: list[Exception_] = Field(default_factory=list)
    website: Optional[str] = None
    owner_whatsapp: Optional[str] = None
    source: str = ""
    note: Optional[str] = None
    exceptions: list[Exception_] = Field(default_factory=list)  # exception hours already set for the coming year (suggest builder)


class Holiday(BaseModel):
    date: str
    name_fi: str
    name_en: str
    public_holiday: bool
    weekday: str  # mon..sun


class Detection(BaseModel):
    business_id: str
    holiday_date: str
    signals: dict = Field(default_factory=lambda: {
        "regular_that_day": None, "last_year": None, "website": None,
        "google_now": None, "peers": None})
    reason_codes: list[str] = Field(default_factory=list)
    holiday: Optional[dict] = None  # {date, name_fi, name_en, public_holiday, weekday}, added by the detect builder
    status: str = "ok"              # "ok" | "past" (the date is before today)


class Reason(BaseModel):
    source: str
    dataset_id: str = ""
    text_fi: str
    text_en: str


class ChannelLog(BaseModel):
    channel: str
    at: str
    detail: str = ""


class Suggestion(BaseModel):
    id: str
    business_id: str
    holiday_date: str
    kind: Literal["hours", "closed", "no_change", "ask"]
    proposed: Optional[list[Span]] = None
    confidence: float = Field(ge=0, le=1)
    reasons: list[Reason] = Field(default_factory=list)
    message_fi: str = ""
    message_en: str = ""
    status: Literal["proposed", "sent", "approved", "edited", "declined", "applied", "expired"] = "proposed"
    channel_log: list[ChannelLog] = Field(default_factory=list)
    # fields added by the suggest builder for the contact lane and the ask kind
    question_fi: Optional[str] = None
    business_name: Optional[str] = None
    holiday_name_fi: Optional[str] = None
    holiday_name_en: Optional[str] = None
    last_year_hours: Optional[Union[list[Span], Literal["closed"]]] = None
    google_now: Optional[dict] = None
    decide_url: Optional[str] = None
    # set by learn.prefs.apply_prefs
    auto_apply: bool = False
    auto_apply_reason_fi: Optional[str] = None


class Decision(BaseModel):
    suggestion_id: str
    action: Literal["approve", "edit", "decline"]
    edited: Union[list[Span], Literal["closed"], None] = None
    reason_chip: Optional[str] = None
    standing_permission: bool = False
    scope: Literal["same", "all"] = "same"
    via: Literal["whatsapp", "call", "web", "voice"] = "web"
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ApplyResult(BaseModel):
    suggestion_id: str
    yext_status: str
    publishers: list[str] = Field(default_factory=list)
    broker_updated: bool = False
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Event(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step: Literal["detect", "suggest", "contact", "decide", "apply", "learn", "broker"]
    business_id: str = ""
    suggestion_id: str = ""
    title_fi: str
    title_en: str
    detail: dict = Field(default_factory=dict)
    id: Optional[int] = None  # assigned by the store
