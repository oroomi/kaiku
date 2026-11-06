"""Small shared helpers: hours text, suggestion state."""
from __future__ import annotations

import re

PENDING = ("proposed", "sent")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _t(x: str) -> str:
    h, m = x.split(":")
    return str(int(h)) if m == "00" else f"{int(h)}:{m}"


def hours_text(h) -> str:
    """[{start,end}] -> '9-13'; 'closed'/empty -> 'closed'; None -> ''."""
    if h is None:
        return ""
    if h == "closed" or h == []:
        return "closed"
    if isinstance(h, list) and h and isinstance(h[0], dict) and "date" in h[0]:  # a period item: one entry per day
        return "; ".join(f"{d_short(x['date'])} {hours_text(x.get('proposed'))}".strip() for x in h)
    return ", ".join(f"{_t(s['start'])}-{_t(s['end'])}" for s in h)


def d_short(iso: str) -> str:
    return f"{int(iso[8:10])}.{int(iso[5:7])}."


def is_pending(item: dict) -> bool:
    return item.get("status", "proposed") in PENDING


def validate_hours(edited):
    """-> 'closed' | [{start,end}] | None (invalid)."""
    if edited == "closed":
        return "closed"
    if not isinstance(edited, list) or not edited:
        return None
    out = []
    for sp in edited:
        try:
            s, e = sp["start"], sp["end"]
        except (KeyError, TypeError):
            return None
        if not (HHMM.match(s) and HHMM.match(e)) or s >= e:
            return None
        out.append({"start": s, "end": e})
    return out
