"""Aura: proposals (pending, in a small json store) and real NGSI-LD subscriptions on Orion-LD."""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

import httpx

from . import models

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "aura_cache" / "subs.json"
BROKER = os.environ.get("KAIKU_BROKER_URL", "http://127.0.0.1:1026").rstrip("/")
NG = BROKER + "/ngsi-ld/v1"
_lock = threading.Lock()


def notify_uri() -> str:
    base = os.environ.get("AURA_NOTIFY_BASE") or os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210"
    return base.rstrip("/") + "/aura/notify"


def _load() -> dict:
    try:
        return json.loads(STORE.read_text())
    except (OSError, ValueError):
        return {"proposals": {}, "active": {}}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1))


def new_proposal(args: dict) -> dict:
    p = {"id": uuid.uuid4().hex[:10], "status": "pending", **args}
    with _lock:
        d = _load()
        d["proposals"][p["id"]] = p
        _save(d)
    return p


def get_proposal(pid: str) -> dict | None:
    return _load()["proposals"].get(pid)


def reject(pid: str) -> bool:
    with _lock:
        d = _load()
        p = d["proposals"].get(pid)
        if not p or p["status"] != "pending":
            return False
        p["status"] = "rejected"
        _save(d)
    return True


def approve(pid: str) -> dict:
    """The human tap: create the real subscription. Raises KeyError / ValueError / httpx.HTTPError."""
    with _lock:
        d = _load()
        p = d["proposals"].get(pid)
        if not p:
            raise KeyError(pid)
        if p["status"] != "pending":
            raise ValueError(f"proposal is {p['status']}")
        body = models.subscription_body(p, notify_uri())
        body["id"] = f"urn:ngsi-ld:Subscription:aura-{pid}"
        r = httpx.post(f"{NG}/subscriptions", json=body, timeout=5,
                       headers={"Content-Type": "application/json", "Link": models.link(models.SDM_TRANSPORT)})
        if r.status_code not in (201, 204):
            raise httpx.HTTPError(f"Orion {r.status_code}: {r.text[:200]}")
        p["status"] = "approved"
        p["subscription_id"] = body["id"]
        d["active"][body["id"]] = p
        _save(d)
    return {"proposal": p, "subscription": body}


def by_subscription(sid: str) -> dict | None:
    d = _load()
    return d["active"].get(sid)


def list_active() -> list[dict]:
    d = _load()
    live = {}
    try:
        r = httpx.get(f"{NG}/subscriptions", timeout=3, headers={"Accept": "application/json"})
        live = {s["id"]: s for s in r.json()} if r.status_code == 200 else {}
    except httpx.HTTPError:
        pass
    out = []
    for sid, p in d["active"].items():
        s = live.get(sid)
        if live and not s:
            continue
        n = (s or {}).get("notification", {})
        out.append({**p, "subscription_id": sid, "times_sent": n.get("timesSent"), "last_notification": n.get("lastNotification"),
                    "status_orion": (s or {}).get("status")})
    return out


def delete(sid: str) -> None:
    httpx.delete(f"{NG}/subscriptions/{sid}", timeout=3)
    with _lock:
        d = _load()
        d["active"].pop(sid, None)
        _save(d)
