"""JSON endpoints for the clock and learned prefs."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import prefs, timetravel

router = APIRouter()


def _state() -> dict:
    return {"today": timetravel.today().isoformat(), "fake": timetravel.is_fake()}


def _tt(d: Optional[str]) -> dict:
    if d is not None:
        d = d.strip()
        if d in ("", "real"):
            timetravel.clear()
        else:
            try:
                timetravel.set_today(date.fromisoformat(d))
            except ValueError:
                raise HTTPException(400, "date must be YYYY-MM-DD or 'real'")
    return _state()


@router.get("/api/timetravel")
def tt_get(date: Optional[str] = Query(None)):
    return _tt(date)


@router.post("/api/timetravel")
def tt_post(date: Optional[str] = Query(None)):
    return _tt(date)


@router.get("/api/learn/prefs/{business_id}")
def prefs_get(business_id: str):
    return prefs.get_prefs(business_id)


@router.post("/api/learn/decision")
def decision_post(body: dict = Body(...)):
    try:
        bid, sug, dec = body["business_id"], body["suggestion"], body["decision"]
    except KeyError as e:
        raise HTTPException(422, f"missing {e}")
    stored = prefs.record_decision(bid, sug, dec)
    return {"prefs": stored, "suggestion": prefs.apply_prefs(bid, sug)}
