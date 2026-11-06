"""SQLite app state (WAL). JSON columns. Seed loader for data/furry_paw.json."""
from __future__ import annotations

import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Optional

from .config import settings
from .schema import Business, Decision, Event, Suggestion

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suggestions (id TEXT PRIMARY KEY, business_id TEXT, holiday_date TEXT,
  status TEXT, data TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, suggestion_id TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, step TEXT, business_id TEXT,
  suggestion_id TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(SCHEMA)
    return _conn


def reset(path=None):
    """Close the connection (tests point KAIKU_DB elsewhere and call this)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        if path is not None:
            settings.DB_PATH = path


def _q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, args).fetchall()


def _x(sql: str, args: tuple = ()) -> int:
    with _lock:
        return conn().execute(sql, args).lastrowid


# businesses
def seed(force: bool = False) -> Business:
    """Load data/furry_paw.json; owner_whatsapp comes from env, never from the file."""
    raw = json.loads((settings.DATA_DIR / "furry_paw.json").read_text())
    raw["owner_whatsapp"] = settings.OWNER_WHATSAPP or None
    raw["owner_email"] = os.getenv("OWNER_EMAIL") or raw.get("owner_email")
    b = Business.model_validate(raw)
    if force or not _q("SELECT 1 FROM businesses WHERE id=?", (b.id,)):
        save_business(b)
    return b


def save_business(b: Business) -> None:
    _x("INSERT OR REPLACE INTO businesses(id,data) VALUES(?,?)", (b.id, b.model_dump_json()))


def get_business(bid: str) -> Optional[Business]:
    r = _q("SELECT data FROM businesses WHERE id=?", (bid,))
    return Business.model_validate_json(r[0]["data"]) if r else None


def list_businesses() -> list[Business]:
    return [Business.model_validate_json(r["data"]) for r in _q("SELECT data FROM businesses")]


# suggestions
def save_suggestion(s: Suggestion) -> None:
    _x("INSERT OR REPLACE INTO suggestions(id,business_id,holiday_date,status,data,updated) "
       "VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)", (s.id, s.business_id, s.holiday_date, s.status, s.model_dump_json()))


def get_suggestion(sid: str) -> Optional[Suggestion]:
    r = _q("SELECT data FROM suggestions WHERE id=?", (sid,))
    return Suggestion.model_validate_json(r[0]["data"]) if r else None


def list_suggestions(business_id: Optional[str] = None, limit: int = 50) -> list[Suggestion]:
    if business_id:
        rows = _q("SELECT data FROM suggestions WHERE business_id=? ORDER BY rowid DESC LIMIT ?", (business_id, limit))
    else:
        rows = _q("SELECT data FROM suggestions ORDER BY rowid DESC LIMIT ?", (limit,))
    return [Suggestion.model_validate_json(r["data"]) for r in rows]


# decisions
def save_decision(d: Decision) -> None:
    _x("INSERT INTO decisions(suggestion_id,data) VALUES(?,?)", (d.suggestion_id, d.model_dump_json()))


def get_decisions(suggestion_id: str) -> list[Decision]:
    return [Decision.model_validate_json(r["data"]) for r in
            _q("SELECT data FROM decisions WHERE suggestion_id=? ORDER BY id", (suggestion_id,))]


# events
def save_event(e: Event) -> Event:
    e.id = _x("INSERT INTO events(ts,step,business_id,suggestion_id,data) VALUES(?,?,?,?,?)",
              (e.ts, e.step, e.business_id, e.suggestion_id, e.model_dump_json()))
    return e


def recent_events(limit: int = 50, after_id: int = 0) -> list[Event]:
    rows = _q("SELECT id,data FROM events WHERE id>? ORDER BY id DESC LIMIT ?", (after_id, limit))
    out = []
    for r in reversed(rows):
        e = Event.model_validate_json(r["data"])
        e.id = r["id"]
        out.append(e)
    return out


# prefs
def get_pref(key: str, default: Any = None) -> Any:
    r = _q("SELECT value FROM prefs WHERE key=?", (key,))
    return json.loads(r[0]["value"]) if r else default


def set_pref(key: str, value: Any) -> None:
    _x("INSERT OR REPLACE INTO prefs(key,value) VALUES(?,?)", (key, json.dumps(value)))


def clear_runs(business_id: str) -> dict:
    """Demo reset: drop the business's suggestions, their decisions, and all events."""
    with _lock:
        ids = [r["id"] for r in _q("SELECT id FROM suggestions WHERE business_id=?", (business_id,))]
        for sid in ids:
            _x("DELETE FROM decisions WHERE suggestion_id=?", (sid,))
        _x("DELETE FROM suggestions WHERE business_id=?", (business_id,))
        n = len(_q("SELECT id FROM events"))
        _x("DELETE FROM events")  # single-business demo: every event goes, including strays from other modules
    return {"suggestions": len(ids), "events": n}
