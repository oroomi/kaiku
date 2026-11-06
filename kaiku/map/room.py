"""Room state: who owns which business, what they answered. data/room_state.json, written atomically."""
from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import osm

_lock = threading.RLock()
_cache: dict = {}
HOLIDAY = "2026-12-24"
NOTE = "demo: answers from the room are not written to Yext; the sandbox has one entity"


def state_path() -> Path:
    return osm.data_dir() / "room_state.json"


def _empty() -> dict:
    return {"answers": {}, "assignments": {}, "updated_at": None}


def load_state() -> dict:
    p = state_path()
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return _empty()


def save_state(st: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False))
    tmp.replace(p)


def businesses() -> list[dict]:
    """Cached businesses ordered by distance from the centre (first owners land in the middle of the screen)."""
    p = osm.cache_path()
    key = (str(p), p.stat().st_mtime if p.exists() else 0)
    if _cache.get("key") != key:
        doc = osm.load()
        lat0, lon0 = osm.CENTER
        items = sorted(doc["businesses"], key=lambda b: math.hypot((b["lat"] - lat0) * 111.3, (b["lon"] - lon0) * 55.3))
        _cache.update(key=key, items=items, meta={k: v for k, v in doc.items() if k != "businesses"})
    return _cache["items"]


def meta() -> dict:
    businesses()
    return _cache["meta"]


def by_id(bid: str) -> dict | None:
    return next((b for b in businesses() if b["id"] == bid), None)


def parse_answer(text: str) -> dict:
    """Chips and free text to {kind, display, hours}. Never invents: unknown text is kept as typed."""
    t = (text or "").replace("–", "-").replace("—", "-")
    # explicit whitelist: letters, digits, space, colon, dot, hyphen (HTML is escaped on render, never stripped there)
    t = "".join(ch for ch in t if ch.isalnum() or ch in " :.-").strip()[:40]
    low = t.lower()
    m = re.search(r"(\d{1,2})(?:[:.](\d\d))?\s*-\s*(\d{1,2})(?:[:.](\d\d))?", t)
    if re.search(r"suljettu|kiinni|closed", low):
        return {"kind": "closed", "display": "suljettu", "hours": "closed"}
    if "normaal" in low:
        return {"kind": "regular", "display": "normaalisti", "hours": "regular"}
    if m:
        a = f"{int(m[1])}" + (f":{m[2]}" if m[2] and m[2] != "00" else "")
        b = f"{int(m[3])}" + (f":{m[4]}" if m[4] and m[4] != "00" else "")
        return {"kind": "hours", "display": f"{a}-{b}", "hours": f"{a}-{b}"}
    return {"kind": "other", "display": t or "?", "hours": None}


def assign(token: str) -> dict | None:
    """Sticky round robin: the next business that is unanswered and not held by another visitor."""
    with _lock:
        st = load_state()
        bid = st["assignments"].get(token)
        if bid and by_id(bid):
            return by_id(bid)
        held = set(st["assignments"].values())
        pool = [b for b in businesses() if not b.get("holiday_hours_found")]
        pick = next((b for b in pool if b["id"] not in held and b["id"] not in st["answers"]), None) \
            or next((b for b in pool if b["id"] not in st["answers"]), None)
        if pick is None:
            return None
        st["assignments"][token] = pick["id"]
        save_state(st)
        return pick


def record(bid: str, text: str, token: str = "") -> dict:
    with _lock:
        st = load_state()
        a = parse_answer(text)
        a.update(at=datetime.now(timezone.utc).isoformat(), raw=(text or "")[:40])
        st["answers"][bid] = a
        if token:
            st["assignments"][token] = bid
        save_state(st)
        return a


def reset() -> None:
    with _lock:
        save_state(_empty())


def snapshot() -> dict:
    st = load_state()
    biz = businesses()
    out = []
    for b in biz:
        a = st["answers"].get(b["id"])
        status = "answered" if a else ("known" if b.get("holiday_hours_found") else "unknown")
        row = {"id": b["id"], "n": b["name"], "c": b["category"], "lat": b["lat"], "lon": b["lon"], "s": status}
        if a:
            row["a"] = a["display"]
        out.append(row)
    ans = sum(1 for r in out if r["s"] == "answered")
    known = sum(1 for r in out if r["s"] == "known")
    latest = sorted(((r["n"], r["a"], st["answers"][r["id"]]["at"]) for r in out if r["s"] == "answered"),
                    key=lambda x: x[2], reverse=True)[:8]
    return {"businesses": out, "counts": {"total": len(out), "answered": ans, "known": known,
                                          "unknown": len(out) - ans - known},
            "latest": [{"name": n, "answer": a, "at": t} for n, a, t in latest], "meta": meta()}
