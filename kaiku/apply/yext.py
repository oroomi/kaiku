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
REVIEWS_BASE = "https://sbx-api.yextapis.com/v2/accounts/me"  # the Reviews API lives on the sandbox gateway
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


def reply_log_path() -> Path:
    """Where approved review replies go when the key cannot post comments (KAIKU_REPLIES_FILE overrides, for tests)."""
    return Path(os.environ.get("KAIKU_REPLIES_FILE") or (DATA_DIR / "review_replies.jsonl"))


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

    def _req(self, method: str, path: str, body: dict | None = None, base: str | None = None, query: dict | None = None) -> dict:
        try:
            r = httpx.request(method, f"{base or self.base}{path}", params={"api_key": self._key, "v": API_VERSION, **(query or {})},
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

    # ---------- description ----------
    def get_description(self, entity_id: str) -> str:
        return (self.get_entity(entity_id).get("description") or "").strip()

    def set_description(self, entity_id: str, text: str) -> dict:
        """PUT only the description field (other fields stay), read it back. Raises YextError when not verified."""
        self.update_entity(entity_id, {"description": text})
        back = self.get_description(entity_id)
        if back != text.strip():
            raise YextError("description not verified on read-back")
        return {"description": back}

    # ---------- reviews (sandbox gateway) ----------
    def list_reviews(self, entity_id: str) -> list[dict]:
        res = self._req("GET", "/reviews", base=REVIEWS_BASE, query={"entityIds": entity_id})
        return res.get("reviews") or []

    def create_review(self, entity_id: str, author: str, content: str, rating: int) -> str:
        res = self._req("POST", "/reviews", {"entityId": entity_id, "authorName": author, "content": content,
                                             "rating": rating, "publisherId": "FIRSTPARTY"}, base=REVIEWS_BASE)
        return str(res.get("id"))

    def post_review_comment(self, review_id: str, content: str) -> dict:
        return self._req("POST", f"/reviews/{review_id}/comments", {"content": content}, base=REVIEWS_BASE)

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
        hours = dict(snap["hours"])
        hours.setdefault("holidayHours", [])  # omitted key keeps the live rows; [] clears them
        res = self.update_entity(entity_id, hours_payload(hours))
        if self.get_hours(entity_id).get("holidayHours", []) != hours["holidayHours"]:
            raise YextError("revert not verified on read-back")
        return res

    def reset_demo(self, entity_id: str) -> dict:
        """Remove ALL holiday rows, keep regular hours, verify by read-back, return the hours."""
        cur = self.get_hours(entity_id)
        new = {k: v for k, v in cur.items() if k != "holidayHours"}
        new["holidayHours"] = []
        self.update_entity(entity_id, hours_payload(new))
        after = self.get_hours(entity_id)
        if after.get("holidayHours"):
            raise YextError("reset not verified: holiday rows remain")
        return after

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


def apply_description(entity_id: str, text: str, client: YextSandbox | None = None) -> dict:
    """PUT the description, read it back, verify. Never raises."""
    out = {"yext_status": "ok", "entity_id": entity_id, "written": text, "verified": False, "environment": "sandbox",
           "what": "description"}
    try:
        text = (text or "").strip()
        if not text or len(text) > 7500:
            raise ValueError("description must be 1-7500 characters")
        c = client or YextSandbox()
        c.update_entity(entity_id, {"description": text})
        ent = c.get_entity(entity_id)
        out["entity_version"] = ent.get("meta", {}).get("timestamp")
        out["verified"] = (ent.get("description") or "").strip() == text
        if not out["verified"]:
            out["yext_status"] = "error:written but not found on read-back"
    except (YextError, ValueError, KeyError, OSError) as e:
        out["yext_status"] = f"error:{e}"
    return out


def apply_review_reply(entity_id: str, review_id: str, text: str, client: YextSandbox | None = None,
                       sample: bool = False) -> dict:
    """Post the reply as a comment on the review. If the key cannot, store it in data/review_replies.jsonl and say so.
    result['posted'] is True only when the read-back shows our comment on the review. Never raises."""
    out = {"yext_status": "ok", "entity_id": entity_id, "review_id": review_id, "written": text, "posted": False,
           "stored": False, "verified": False, "environment": "sandbox", "what": "review_reply", "post_error": None}
    text = (text or "").strip()
    if not text or len(text) > 4000:
        out["yext_status"] = "error:reply must be 1-4000 characters"
        return out
    posted_err = None
    if sample or str(review_id).startswith("sample-"):
        posted_err = "sample review from a file, there is nothing in Yext to comment on"
    else:
        try:
            c = client or YextSandbox()
            c.post_review_comment(review_id, text)
            out["posted"] = True
            try:
                mine = [r for r in c.list_reviews(entity_id) if str(r.get("id")) == str(review_id)]
                out["verified"] = bool(mine) and any((cm.get("content") or "").strip() == text for cm in (mine[0].get("comments") or []))
            except YextError:
                pass
        except (YextError, KeyError) as e:
            posted_err = str(e)
    if not out["posted"]:
        out["post_error"] = posted_err
        try:
            p = reply_log_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as f:
                f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "entity_id": entity_id, "review_id": review_id,
                                    "reply": text, "posted": False, "post_error": posted_err}, ensure_ascii=False) + "\n")
            out["stored"] = True
        except OSError as e:
            out["yext_status"] = f"error:{e}"
    return out
