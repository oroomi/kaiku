"""Stand-in for kaiku.suggest.feed, used ONLY when that module cannot be imported.

Contract (same as GET /api/feed/{business_id}):
  {"suggestions":[{"id","kind": "holiday_hours|conflict|period|no_change","title_en","text_en","proposed",
                   "confidence","reasons":[{"source","text_en"}],"status"}]}
Extra optional keys the chat reads when present: holiday_date, holiday_name_en, last_year, members.
Everything here comes from the business record, the holiday calendar and the stored suggestions; nothing is invented.
Set KAIKU_FEED_FIXTURE=/path/feed.json to serve a fixed feed (demo and screenshots).
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

from .util import d_short, hours_text

WD = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WINDOW_DAYS = 12


def _spans(h):
    return [{"start": s.start, "end": s.end} for s in h] if h else []


def _last_year(b, iso: str):
    md = iso[5:]
    for e in b.last_year_exceptions:
        if e.date[5:] == md and e.date[:4] < iso[:4]:
            return "closed" if e.hours == "closed" else _spans(e.hours)
    return None


def _regular(b, iso: str):
    return _spans(b.regular_hours.get(WD[date.fromisoformat(iso).weekday()], []))


def _stored(store, bid: str) -> dict:
    out: dict = {}
    for s in store.list_suggestions(bid, 50):  # newest first
        out.setdefault(s.holiday_date, s)
    return out


def _item_for(b, h, stored) -> dict | None:
    iso = h.date
    ly, reg = _last_year(b, iso), _regular(b, iso)
    st = stored.get(iso)
    name = h.name_en
    base = {"holiday_date": iso, "holiday_name_en": name, "last_year": ly}
    if st is not None and st.status != "expired":
        kind = {"hours": "holiday_hours", "closed": "holiday_hours", "no_change": "no_change"}.get(st.kind, "holiday_hours")
        prop = "closed" if st.kind == "closed" else ([x.model_dump() for x in st.proposed] if st.proposed else None)
        status = {"approved": "approved", "edited": "approved", "applied": "approved", "declined": "declined"}.get(st.status, "proposed")
        if kind == "no_change":
            text = st.message_en or f"{name} {d_short(iso)}: nothing to change."
        elif ly is not None:
            text = (f"Last year you were {'closed' if ly == 'closed' else 'open ' + hours_text(ly)}. "
                    f"Connect still publishes {hours_text(reg) or 'closed'} for that day.")
        else:
            text = st.reasons[0].text_en if st.reasons else (st.message_en or "")
        return {"id": st.id, "kind": kind, "title_en": f"{name} {d_short(iso)}" + (" hours are missing" if kind != "no_change" else ""), "text_en": text,
                "proposed": prop, "confidence": st.confidence, "status": status,
                "reasons": [{"source": r.source, "text_en": r.text_en} for r in st.reasons], **base}
    if not h.public_holiday and not reg:
        why = f"the clinic is closed on {['Mondays','Tuesdays','Wednesdays','Thursdays','Fridays','Saturdays','Sundays'][date.fromisoformat(iso).weekday()]}"
        return {"id": f"stub-{iso}", "kind": "no_change", "title_en": f"{name} {d_short(iso)}",
                "text_en": f"{name} {d_short(iso)} is not a public holiday and {why}. Nothing to change.",
                "proposed": None, "confidence": 0.95, "status": "proposed",
                "reasons": [{"source": "calendar", "text_en": "Flag day, not a public holiday"}], **base}
    if ly is None:
        return None  # cold start: no history, no guess
    txt = f"Last year you were {'closed' if ly == 'closed' else 'open ' + hours_text(ly)}. Connect still publishes {hours_text(reg) or 'closed'} for that day."
    return {"id": f"stub-{iso}", "kind": "holiday_hours", "title_en": f"{name} {d_short(iso)} hours are missing",
            "text_en": txt, "proposed": ly, "confidence": 0.6, "status": "proposed",
            "reasons": [{"source": "last_year", "text_en": f"Last year {hours_text(ly)}"}], **base}


def get_feed(business_id: str) -> dict:
    fx = os.environ.get("KAIKU_FEED_FIXTURE")
    if fx:
        try:
            return json.loads(open(fx, encoding="utf-8").read())
        except (OSError, ValueError):
            pass
    from .. import store
    from ..detect import holidays
    from ..learn import timetravel
    b = store.get_business(business_id)
    if b is None:
        return {"suggestions": []}
    stored = _stored(store, business_id)
    items = []
    for h in holidays.upcoming(timetravel.today(), WINDOW_DAYS):
        it = _item_for(b, h, stored)
        if it:
            items.append(it)
    # bundle neighbouring "closed" holidays into one period item (25.12. and 26.12. read as one thing)
    out, run = [], []

    def flush():
        if len(run) >= 2:
            ids = [r["id"] for r in run]
            a, z = run[0]["holiday_date"], run[-1]["holiday_date"]
            out.append({"id": "period-" + a, "kind": "period", "title_en": f"Christmas period {d_short(a)} to {d_short(z)}",
                        "text_en": f"Last year you were closed on {d_short(a)} and {d_short(z)}. I suggest the same.",
                        "proposed": "closed", "confidence": min(r["confidence"] for r in run), "status": run[0]["status"],
                        "reasons": run[0]["reasons"], "members": ids, "holiday_date": a, "holiday_name_en": "Christmas period",
                        "last_year": "closed"})
        else:
            out.extend(run)
        run.clear()
    for it in items:
        if it["kind"] == "holiday_hours" and it["proposed"] == "closed" and it.get("last_year") == "closed":
            if run and (date.fromisoformat(it["holiday_date"]) - date.fromisoformat(run[-1]["holiday_date"]) > timedelta(days=1)
                        or run[-1]["status"] != it["status"]):
                flush()
            run.append(it)
        else:
            flush()
            out.append(it)
    flush()
    return {"suggestions": out}
