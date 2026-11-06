"""detect(business, holiday_date, now) -> Detection: collects every signal and names the reason codes."""
from __future__ import annotations

from datetime import date

from kaiku.detect import holidays as hol
from kaiku.detect import signals as sg
from kaiku.suggest.schema import Business, Detection, Holiday, valid_hours


def _holiday(d: str) -> Holiday:
    h = hol.get(d)
    if h is None:  # an ordinary day: still detectable (e.g. a custom closure)
        dd = date.fromisoformat(d)
        h = Holiday(d, "", "", False, hol.WD_FI[dd.weekday()])
    return h


def _as_date(x) -> date | None:
    if x is None or x == "":
        return None
    return x if isinstance(x, date) else date.fromisoformat(x)


def detect(business: Business, holiday_date, now=None, use_network: bool = True) -> Detection:
    iso = holiday_date if isinstance(holiday_date, str) else holiday_date.isoformat()
    h = _holiday(iso)
    today = _as_date(now)
    if today is not None and date.fromisoformat(iso) < today:
        # the date has passed: no signals are collected and nothing may be suggested
        return Detection(business.id, iso, {"regular_that_day": sg.regular_that_day(business, iso),
                                            "last_year": {"found": False}, "website": None,
                                            "google_now": {"status": "unknown"}, "peers": None, "this_year": None},
                         ["PAST_DATE"], h.to_dict(), status="past")
    s = {
        "regular_that_day": sg.regular_that_day(business, iso),
        "last_year": sg.last_year(business, h) if h.name_fi else {"found": False},
        "website": sg.website(business, h) if (use_network and h.name_fi) else None,
        "google_now": sg.google_now(business, iso) if use_network else {"status": "unknown"},
        "peers": sg.peers(business, h) if h.name_fi else None,
    }
    this_year = next((e for e in business.exceptions if e.get("date") == iso and valid_hours(e.get("hours"))), None)
    s["this_year"] = this_year
    codes = []
    if h.public_holiday:
        codes.append("PUBLIC_HOLIDAY")
    else:
        codes.append("NOT_PUBLIC_HOLIDAY")
    if s["regular_that_day"]["closed"]:
        codes.append("REGULAR_CLOSED_THAT_DAY")
    if s["last_year"].get("found"):
        codes.append("LAST_YEAR_FOUND")
    if this_year:
        codes.append("EXCEPTION_ALREADY_SET")
    else:
        codes.append("NO_EXCEPTION_THIS_YEAR")
    if s["website"]:
        codes.append("WEBSITE_SAYS")
    if s["google_now"].get("status") == "shows_hours":
        codes.append("GOOGLE_SHOWS_REGULAR" if s["google_now"].get("hours") == s["regular_that_day"]["hours"] else "GOOGLE_SHOWS_HOURS")
    elif not this_year:
        codes.append("CONNECT_SHOWS_REGULAR")  # Connect publishes the regular hours unless an exception is set; Google not verified
    if s["peers"]:
        codes.append("PEER_PRIOR")
    return Detection(business.id, iso, s, codes, h.to_dict())
