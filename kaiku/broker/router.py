"""POST /broker/notify receives NGSI-LD notifications and turns them into chain events."""
from __future__ import annotations

import logging

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
                   suggestion_id=None, title_fi=title_fi, title_en=title_en, detail=detail)
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
        st = ent.get("holidayHoursStatus")
        for inst in as_list(st) if st else []:
            v = inst.get("value") or {}
            if v.get("status") == "missing":
                key = (biz, "missing", v.get("date"), inst.get("observedAt"))
                if inst.get("observedAt") and _seen.get(key[:3]) == key[3]:
                    continue
                _seen[key[:3]] = inst.get("observedAt")
                fi, en = holiday_label(v.get("date"))
                _emit("broker", biz, f"Tilaus laukesi: {fi} aukioloajat puuttuvat",
                      f"Subscription fired: {en} hours missing",
                      {"kind": "missing", "date": v.get("date"), "subscriptionId": note.get("subscriptionId")})
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
            fi, en = holiday_label(v.get("date"))
            _emit("broker", biz, f"Tilaus laukesi: {fi} aukioloajat vahvistettu",
                  f"Subscription fired: {en} hours resolved", {"kind": "resolved", "value": v,
                                                             "subscriptionId": note.get("subscriptionId")})
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
