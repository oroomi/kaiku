"""Yext SANDBOX client for the APPLY step. Never talks to production."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://api-sandbox.yext.com/v2/accounts/me"
API_VERSION = "20241101"
TIMEOUT = 10.0
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class YextError(RuntimeError):
    pass


def _load_key() -> str:
    key = os.environ.get("YEXT_API_KEY")
    if not key:
        try:
            from dotenv import dotenv_values
            for p in (Path(__file__).resolve().parents[2] / ".env", Path("/root/hack/kaiku/.env")):
                if p.exists():
                    key = dotenv_values(p).get("YEXT_API_KEY")
                    if key:
                        break
        except ImportError:
            pass
    if not key:
        raise YextError("YEXT_API_KEY missing")
    return key


def has_key() -> bool:
    try:
        _load_key()
        return True
    except YextError:
        return False


# ---------- payload builders (pure, no network) ----------
def holiday_row(date: str, proposed=None) -> dict:
    """proposed: [{start,end}] | "closed" | None(=closed). Validates locally because
    the sandbox accepts inverted intervals (13:00-09:00) with HTTP 200."""
    if not _DATE.match(date):
        raise ValueError(f"date must be YYYY-MM-DD, got {date!r}")
    datetime.strptime(date, "%Y-%m-%d")
    if proposed is None or proposed == "closed":
        return {"date": date, "isClosed": True}
    ivs = []
    for iv in proposed:
        s, e = iv["start"], iv["end"]
        if not (_TIME.match(s) and _TIME.match(e)):
            raise ValueError(f"times must be HH:MM, got {s!r}-{e!r}")
        if s >= e:
            raise ValueError(f"start must be before end, got {s}-{e}")
        ivs.append({"start": s, "end": e})
    if not ivs:
        return {"date": date, "isClosed": True}
    return {"date": date, "openIntervals": ivs}


def merge_holiday_rows(existing: list[dict], rows: list[dict], merge: bool = True) -> list[dict]:
    by = {r["date"]: r for r in (existing if merge else [])}
    for r in rows:
        by[r["date"]] = r
    return [by[d] for d in sorted(by)]


def hours_payload(hours: dict) -> dict:
    """Body for PUT /entities/{id}. holidayHours lives INSIDE hours; top-level holidayHours is rejected."""
    return {"hours": hours}


REGULAR_HOURS = {
    **{d: {"openIntervals": [{"start": "09:00", "end": "17:00"}]} for d in DAYS[:5]},
    "saturday": {"openIntervals": [{"start": "10:00", "end": "14:00"}]},
    "sunday": {"isClosed": True},
}


class YextSandbox:
    def __init__(self, api_key: str | None = None, base: str = BASE, timeout: float = TIMEOUT):
        self._key = api_key or _load_key()
        self.base = base
        self.timeout = timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            r = httpx.request(method, f"{self.base}{path}", params={"api_key": self._key, "v": API_VERSION},
                              json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise YextError(f"network: {type(e).__name__}") from None
        try:
            j = r.json()
        except ValueError:
            raise YextError(f"HTTP {r.status_code}: non-JSON reply") from None
        errs = j.get("meta", {}).get("errors", [])
        if r.status_code >= 400 or any(x.get("type") == "FATAL_ERROR" for x in errs):
            msg = "; ".join(x.get("message", "?") for x in errs) or f"HTTP {r.status_code}"
            raise YextError(f"HTTP {r.status_code}: {msg}")
        return j.get("response", {})

    def get_entity(self, entity_id: str) -> dict:
        return self._req("GET", f"/entities/{entity_id}")

    def update_entity(self, entity_id: str, fields: dict) -> dict:
        return self._req("PUT", f"/entities/{entity_id}", fields)

    def get_hours(self, entity_id: str) -> dict:
        return self.get_entity(entity_id).get("hours", {}) or {}

    def snapshot(self, entity_id: str) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        p = DATA_DIR / f"yext_snapshot_{ts}.json"
        p.write_text(json.dumps({"entity_id": entity_id, "hours": self.get_hours(entity_id)}, indent=2))
        return p

    def revert(self, entity_id: str, snapshot_file) -> dict:
        snap = json.loads(Path(snapshot_file).read_text())
        if snap.get("entity_id") not in (None, entity_id):
            raise YextError("snapshot belongs to another entity")
        return self.update_entity(entity_id, hours_payload(snap["hours"]))

    def set_hours(self, entity_id: str, hours: dict) -> dict:
        """Replaces regular hours, keeping existing holidayHours unless `hours` carries its own."""
        cur = self.get_hours(entity_id)
        new = dict(hours)
        if "holidayHours" not in new and cur.get("holidayHours"):
            new["holidayHours"] = cur["holidayHours"]
        return self.update_entity(entity_id, hours_payload(new))

    def set_holiday_hours(self, entity_id: str, rows: list[dict], merge: bool = True) -> dict:
        cur = self.get_hours(entity_id)
        new = {k: v for k, v in cur.items() if k != "holidayHours"}
        new["holidayHours"] = merge_holiday_rows(cur.get("holidayHours", []), rows, merge)
        return self.update_entity(entity_id, hours_payload(new))

    def remove_holiday_hours(self, entity_id: str, date: str) -> dict:
        cur = self.get_hours(entity_id)
        new = {k: v for k, v in cur.items() if k != "holidayHours"}
        left = [r for r in cur.get("holidayHours", []) if r.get("date") != date]
        new["holidayHours"] = left  # must send [] explicitly: omitting the key keeps the old rows
        return self.update_entity(entity_id, hours_payload(new))


def apply_suggestion(entity_id: str, holiday_date: str, proposed, client: YextSandbox | None = None) -> dict:
    """proposed: [{start,end}] | "closed". Snapshot, write, GET back, verify. Never raises."""
    out = {"yext_status": "ok", "entity_id": entity_id, "date": holiday_date, "written": None,
           "entity_version": None, "snapshot": None, "verified": False, "environment": "sandbox"}
    try:
        row = holiday_row(holiday_date, proposed)
        out["written"] = row
        c = client or YextSandbox()
        out["snapshot"] = str(c.snapshot(entity_id))
        c.set_holiday_hours(entity_id, [row])
        ent = c.get_entity(entity_id)
        out["entity_version"] = ent.get("meta", {}).get("timestamp")
        rows = (ent.get("hours") or {}).get("holidayHours", [])
        out["verified"] = any(r.get("date") == holiday_date and
                              r.get("isClosed", False) == row.get("isClosed", False) and
                              r.get("openIntervals") == row.get("openIntervals") for r in rows)
        if not out["verified"]:
            out["yext_status"] = "error:written but not found on read-back"
    except (YextError, ValueError, KeyError, OSError) as e:
        out["yext_status"] = f"error:{e}"
    return out
