"""Magic-link tokens for the owner phone page. Single use, 7-day expiry.
Stored in <KAIKU_DATA_DIR or repo data>/decide_tokens.json (atomic writes)."""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

TTL_S = 7 * 24 * 3600
_lock = threading.Lock()


def _file() -> Path:
    d = os.environ.get("KAIKU_DATA_DIR")
    p = Path(d) if d else Path(__file__).resolve().parents[2] / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "decide_tokens.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(obj: dict) -> None:
    path = _file()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def issue(suggestion_id: str, business_id: str) -> str:
    """Return the live unused token for this suggestion, or mint one (so contact and decide share one link)."""
    with _lock:
        db = _read()
        now = time.time()
        for t, r in db.items():
            if r["suggestion_id"] == suggestion_id and not r.get("used") and r["expires"] > now:
                return t
        t = secrets.token_urlsafe(16)
        db[t] = {"suggestion_id": suggestion_id, "business_id": business_id, "used": False, "created": now, "expires": now + TTL_S}
        _write(db)
        return t


def lookup(token: str) -> Optional[dict]:
    """{suggestion_id, business_id, used, expired, decision} or None for an unknown token."""
    r = _read().get(token)
    if not r:
        return None
    return {"suggestion_id": r["suggestion_id"], "business_id": r["business_id"], "used": bool(r.get("used")),
            "expired": r["expires"] < time.time(), "decision": r.get("decision")}


def mark_used(token: str, decision: Optional[dict] = None) -> bool:
    """Atomically claim the token. False if it was already used."""
    with _lock:
        db = _read()
        r = db.get(token)
        if not r or r.get("used"):
            return False
        r["used"] = True
        r["decision"] = decision
        _write(db)
        return True


def link_for(suggestion_id: str, business_id: str) -> str:
    base = os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210"
    return base.rstrip("/") + "/d/" + issue(suggestion_id, business_id)
