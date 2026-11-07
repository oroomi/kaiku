"""POST /broker/notify receives NGSI-LD notifications and turns them into chain events."""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Request

from . import get_broker
from .fallback import as_list
from .subs import ensure_subscriptions

log = logging.getLogger("kaiku.broker")
router = APIRouter()

_seen: dict = {}  # dedupe: Orion-LD re-notifies every instance each time the entity is rewritten

_HOL = {"12-24": ("jouluaaton", "Christmas Eve"), "12-25": ("joulupäivän", "Christmas Day"),
        "12-26": ("tapaninpäivän", "Boxing Day"), "12-31": ("uudenvuodenaaton", "New Year's Eve"),
        "01-01": ("uudenvuodenpäivän", "New Year's Day")}


_emitted: dict = {}
_emit_lock = threading.Lock()
DEDUPE_S = 5.0


def reset_dedupe() -> None:
    with _emit_lock:
        _emitted.clear()
    _seen.clear()


def short_day(date: str | None) -> str:
    """'2026-12-24' -> '24.12.'; empty or malformed -> 'lomapäivä' style neutral label."""
    try:
        return f"{int(date[8:10])}.{int(date[5:7])}."
    except Exception:
        return ""


def emit_once(kind: str, business_id: str, date: str | None, detail: dict | None = None) -> bool:
    """ONE broker event per (business, kind, date) within DEDUPE_S seconds. Used by the notification handler AND by the
    chain, so the subscription firing and the chain's own status write never show up twice."""
    key = (business_id, kind, date or "")
    now = time.monotonic()
    with _emit_lock:
        if now - _emitted.get(key, -1e9) < DEDUPE_S:
            return False
        _emitted[key] = now
    d = short_day(date)
    if kind == "missing":
        fi, en = f"Tilaus laukesi: {d} aukioloajat puuttuvat", f"Subscription fired: {d} hours missing"
    else:
        fi, en = f"Tilaus laukesi: {d} aukioloajat vahvistettu", f"Subscription fired: {d} hours resolved"
    _emit("broker", business_id, fi.replace("  ", " "), en.replace("  ", " "), {"kind": kind, "date": date, **(detail or {})})
    return True


def holiday_label(date: str | None) -> tuple[str, str]:
    if not date:
        return "lomapäivän", "holiday"
    fi_en = _HOL.get(date[5:])
    if fi_en:
        return fi_en
    d = f"{int(date[8:10])}.{int(date[5:7])}."
    return f"päivän {d}", d


def _emit(step, business_id, title_fi, title_en, detail):
    """Emit a chain event if core has landed; otherwise just log."""
    try:
        from kaiku import events  # type: ignore
        from kaiku.schema import Event  # type: ignore
        from datetime import datetime, timezone
        ev = Event(ts=datetime.now(timezone.utc).isoformat(), step=step, business_id=business_id,
                   suggestion_id="", title_fi=title_fi, title_en=title_en, detail=detail)
        events.emit(ev)
        return True
    except Exception as e:  # ImportError or a signature mismatch must never break the broker
        log.info("event (core not wired: %s) %s | %s", type(e).__name__, title_en, detail)
        return False


def handle_notification(note: dict) -> list[dict]:
    """Returns the list of things that fired (also used by tests)."""
    fired = []
    for ent in note.get("data", []):
        biz = ent.get("id", "").rsplit(":", 1)[-1]
        if biz.startswith("osm-"):
            continue  # /city's 813 Turku Stores: POST /city/notify owns their events, so a room answer is not a chain event
        st = ent.get("holidayHoursStatus")
        for inst in as_list(st) if st else []:
            v = inst.get("value") or {}
            if v.get("status") == "missing" and not v.get("seed") and v.get("date"):
                key = (biz, "missing", v.get("date"), inst.get("observedAt"))
                if inst.get("observedAt") and _seen.get(key[:3]) == key[3]:
                    continue
                _seen[key[:3]] = inst.get("observedAt")
                emit_once("missing", biz, v.get("date"), {"subscriptionId": note.get("subscriptionId")})
                fired.append({"kind": "missing", "business": biz, "date": v.get("date")})
        hh = ent.get("holidayHours")
        for inst in as_list(hh) if hh else []:
            if inst.get("datasetId"):
                continue  # a source instance changed; only the default instance is the resolved truth
            v = inst.get("value") or {}
            key = (biz, "resolved", v.get("date"))
            if inst.get("observedAt") and _seen.get(key) == inst.get("observedAt"):
                continue
            _seen[key] = inst.get("observedAt")
            if v.get("seed"):
                continue  # the idle default instance written at start-up or reset is not a decision
            emit_once("resolved", biz, v.get("date"), {"value": v, "subscriptionId": note.get("subscriptionId")})
            fired.append({"kind": "resolved", "business": biz, "value": v})
    return fired


@router.post("/broker/notify")
async def notify(request: Request):
    note = await request.json()
    return {"ok": True, "fired": handle_notification(note)}


@router.get("/broker/status")
def status():
    b = get_broker()
    return {"status": b.status(), "fallback_reason": getattr(b, "fallback_reason", "")}


@router.post("/broker/ensure")
def ensure():
    return {"status": get_broker().status(), "subscriptions": ensure_subscriptions()}


@router.on_event("startup")
def _startup():  # core may also call subs.ensure_subscriptions() from its own lifespan
    try:
        ensure_subscriptions()
    except Exception as e:
        log.warning("subscription setup failed: %s", e)
