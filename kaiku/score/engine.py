"""Listing score 0-100: how up to date and complete the business's information is everywhere Connect publishes.

compute(listing, feed) is pure: `listing` is kaiku.listing.router.normalise() output (the Yext sandbox entity), `feed` is the
suggestions feed. Every check names its source; nothing is guessed. Weights are in docs/score.md and sum to 100.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..chat.util import is_pending

HOLIDAY_KINDS = ("holiday_hours", "conflict", "period")
WEIGHTS = {"hours": 10, "holidays": 30, "agree": 10, "description": 15, "reviews": 15, "address": 10, "contact": 10}
assert sum(WEIGHTS.values()) == 100


def _pending(feed: dict, kind: str | None = None) -> list[dict]:
    return [i for i in feed.get("suggestions", []) if i["kind"] != "no_change" and is_pending(i) and (kind is None or i["kind"] == kind)]


def holiday_dates(feed: dict) -> dict[str, str]:
    """date -> owner state ('open' | 'declined' | 'approved') for every holiday the feed says needs hours."""
    out: dict[str, str] = {}
    for i in feed.get("suggestions", []):
        if i["kind"] not in HOLIDAY_KINDS:
            continue
        if i["kind"] == "period" and isinstance(i.get("proposed"), list):
            ds = [m["date"] for m in i["proposed"] if isinstance(m, dict) and m.get("date") and m.get("kind") != "no_change"]
        else:
            ds = [i["holiday_date"]] if i.get("holiday_date") else []
        for d in ds:
            if out.get(d) != "declined":
                out[d] = "declined" if i.get("status") == "declined" else "open"
    return out


def _dm(iso: str) -> str:
    return f"{int(iso[8:10])}.{int(iso[5:7])}."


def _check(cid, label, points, weight, detail, source) -> dict:
    return {"id": cid, "label_en": label, "ok": points == weight, "points": points, "weight": weight, "detail_en": detail, "source": source}


def compute(listing: dict, feed: dict, now: datetime | None = None, today: str | None = None) -> dict:
    checks = []
    # 1 regular hours: all seven days have a value (open or closed)
    days = [d for d, v in listing["hours"].items() if v is not None]
    ok = len(days) == 7
    checks.append(_check("hours", "Regular opening hours", 10 if ok else 0, 10,
                         "Hours are set for all seven days." if ok else f"Hours are set for {len(days)} of 7 days.", "Yext entity hours"))
    # 2 holiday hours: holidays with a row over holidays the feed detects
    det = holiday_dates(feed)
    rows = {r["date"] for r in listing.get("holiday_hours") or []}
    if det:
        done = [d for d, st in det.items() if d in rows or st == "declined"]
        pts = round(30 * len(done) / len(det))
        missing = sorted(d for d in det if d not in done)
        detail = (f"{len(done)} of {len(det)} upcoming holidays are covered." +
                  (f" Missing: {', '.join(_dm(d) for d in missing)}" if missing else ""))
    else:
        pts, detail = 30, "No upcoming holiday needs hours."
    checks.append(_check("holidays", "Holiday hours for the next holidays", pts, 30, detail, "Yext entity holidayHours, suggestions feed"))
    # 3 sources agree
    conf = _pending(feed, "conflict")
    checks.append(_check("agree", "Sources agree", 0 if conf else 10, 10,
                         f"{len(conf)} conflict{'s' if len(conf) != 1 else ''} waiting for the owner." if conf else "No source conflicts.", "Suggestions feed"))
    # 4 description: present (10) and no pending description suggestion (5)
    desc = bool(listing.get("description")); dpend = _pending(feed, "description")
    pts = (10 if desc else 0) + (0 if dpend else 5)
    checks.append(_check("description", "Business description", pts, 15,
                         ("A description is published." if desc else "No description is published.") +
                         (" A better one is waiting." if dpend else ""), "Yext entity description, suggestions feed"))
    # 5 reviews answered
    rpend = _pending(feed, "review"); rev = listing.get("reviews")
    if rpend:
        detail = f"{len(rpend)} review{'s' if len(rpend) != 1 else ''} waiting for a reply."
    elif rev is not None and rev["count"] == 0:
        detail = "No reviews yet."
    elif rev is None:
        detail = "No review data; no review is waiting in the feed."
    else:
        detail = f"All {rev['count']} reviews are answered."
    checks.append(_check("reviews", "Reviews answered", 0 if rpend else 15, 15, detail, "Yext reviews, suggestions feed"))
    # 6 address and category
    ac = bool(listing.get("address")) and bool(listing.get("categories"))
    miss = [n for n, v in (("address", listing.get("address")), ("category", listing.get("categories"))) if not v]
    checks.append(_check("address", "Address and category", 10 if ac else 0, 10,
                         "Address and category are published." if ac else f"No {' or '.join(miss)} published.", "Yext entity address, categories"))
    # 7 website or phone
    have = [n for n, v in (("website", listing.get("website")), ("phone", listing.get("phone"))) if v]
    checks.append(_check("contact", "Website or phone", 10 if have else 0, 10,
                         f"Published: {' and '.join(have)}." if have else "No website and no phone published.", "Yext entity mainPhone, websiteUrl"))
    score = sum(c["points"] for c in checks)
    label = "Up to date" if score >= 90 else "Mostly up to date" if score >= 60 else "Needs updates"
    return {"business_id": listing.get("business_id"), "score": score, "label_en": label,
            "checks_ok": sum(1 for c in checks if c["ok"]), "checks_total": len(checks), "checks": checks,
            "pending": [i["id"] for i in _pending(feed)],
            "today": today, "as_of": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
