"""The chain: detect > suggest > contact > decide(wait) > apply > learn.

Other modules register real implementations at import time with `chain.register("detect", fn)`.
Until they land, the stubs below produce plausible output from the seed so the UI works.
Step functions may be sync or async.
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException

from . import events, store
from .config import settings
from .schema import (ApplyResult, Business, ChannelLog, Decision, Detection, Event, Reason, Span, Suggestion)

router = APIRouter()
STEP_ORDER = ["detect", "suggest", "contact", "decide", "apply", "learn"]
WD = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FI_WD = ["Maanantaina", "Tiistaina", "Keskiviikkona", "Torstaina", "Perjantaina", "Lauantaina", "Sunnuntaina"]
HOLIDAYS = {  # tiny stub table; the real calendar lives in kaiku/detect/holidays.py
    "12-24": ("Jouluaatto", "Christmas Eve", "Jouluaattona"), "12-25": ("Joulupäivä", "Christmas Day", "Joulupäivänä"),
    "12-26": ("Tapaninpäivä", "Boxing Day", "Tapaninpäivänä"), "12-31": ("Uudenvuodenaatto", "New Year's Eve", "Uudenvuodenaattona"),
    "01-01": ("Uudenvuodenpäivä", "New Year's Day", "Uudenvuodenpäivänä"),
}
_waiters: dict[str, "asyncio.Future[Decision]"] = {}
_stubs: set[str] = set()


# ---------- registry ----------
def _stub(fn):
    _stubs.add(fn.__name__)
    return fn


STEPS: dict[str, Callable] = {}


def register(name: str, fn: Callable) -> None:
    """Replace a step implementation. Called by other modules at import time."""
    if name not in STEP_ORDER:
        raise ValueError(f"unknown step {name}")
    STEPS[name] = fn


def is_stub(name: str) -> bool:
    return getattr(STEPS.get(name), "_kaiku_stub", False)


async def _call(fn, *a):
    r = fn(*a)
    return await r if inspect.isawaitable(r) else r


# ---------- clock (learn.timetravel.today() is THE clock once it lands) ----------
def today() -> date:
    try:
        from .learn import timetravel  # type: ignore
        return timetravel.today()
    except Exception:
        d = store.get_pref("today", "2026-12-17")
        return date.fromisoformat(d)


def fi_date(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"


# ---------- helpers ----------
def fmt_span(spans) -> str:
    if spans == "closed" or not spans:
        return "suljettu"
    return ", ".join(f"{int(s.start[:2])}-{int(s.end[:2])}" if s.start[3:] == "00" and s.end[3:] == "00"
                     else f"{s.start}-{s.end}" for s in spans)


def _ev(step, b: Business, sid: str, fi: str, en: str, **detail) -> Event:
    return events.emit(Event(step=step, business_id=b.id, suggestion_id=sid, title_fi=fi, title_en=en, detail=detail))


# ---------- stub steps ----------
def detect(business: Business, holiday_date: str, now: datetime) -> Detection:
    d = date.fromisoformat(holiday_date)
    ly = next((x for x in business.last_year_exceptions if x.date[5:] == holiday_date[5:] and x.date[:4] < holiday_date[:4]), None)
    reg = business.regular_hours.get(WD[d.weekday()], [])
    return Detection(
        business_id=business.id, holiday_date=holiday_date,
        signals={"regular_that_day": [s.model_dump() for s in reg],
                 "last_year": (ly.model_dump() if ly else None),
                 "website": None, "google_now": None, "peers": None},
        reason_codes=(["last_year_exception"] if ly else []) + (["regular_differs"] if ly and ly.hours != reg else []))


def suggest(business: Business, detection: Detection) -> Suggestion:
    d = date.fromisoformat(detection.holiday_date)
    ly = detection.signals.get("last_year")
    name_fi, name_en, ess = HOLIDAYS.get(detection.holiday_date[5:], ("Pyhäpäivä", "Holiday", "Pyhäpäivänä"))
    reg = [Span(**s) for s in detection.signals.get("regular_that_day") or []]
    reasons: list[Reason] = []
    if ly:
        hours = ly["hours"]
        proposed = None if hours == "closed" else [Span(**s) for s in hours]
        kind = "closed" if hours == "closed" else "hours"
        conf = 0.92
        reasons.append(Reason(source="last_year", dataset_id="urn:kaiku:src:history",
                              text_fi=f"Viime vuonna {ly['date'][8:]}.{ly['date'][5:7]}. aukioloaika oli {fmt_span(proposed or 'closed')}.",
                              text_en=f"Last year on {ly['date'][8:]}.{ly['date'][5:7]}. the hours were {fmt_span(proposed or 'closed')}."))
    else:
        proposed, kind, conf = None, "no_change", 0.88
        reasons.append(Reason(source="regular", dataset_id="urn:kaiku:src:regular",
                              text_fi="Ei viime vuoden poikkeusta, tavalliset aukioloajat.", text_en="No exception last year, regular hours."))
    when = ess if detection.holiday_date[5:] in HOLIDAYS else FI_WD[d.weekday()]
    fi = (f"{when} {business.name} on auki klo {fmt_span(proposed)}. Google näyttää vielä {fmt_span(reg)}."
          if kind == "hours" else f"{when} {business.name} on suljettu." if kind == "closed"
          else f"{business.name} on {FI_WD[d.weekday()].lower()} {'suljettu' if not reg else 'auki klo ' + fmt_span(reg)} kuten aina. Ei muutosta.")
    en = (f"On {name_en}, {business.name} is open {fmt_span(proposed)}. Google still shows {fmt_span(reg)}."
          if kind == "hours" else f"On {name_en}, {business.name} is closed." if kind == "closed" else f"{business.name} keeps its regular hours that day. No change.")
    return Suggestion(id=uuid.uuid4().hex[:10], business_id=business.id, holiday_date=detection.holiday_date, kind=kind,
                      proposed=proposed, confidence=conf, reasons=reasons, message_fi=fi, message_en=en)


def contact(suggestion: Suggestion) -> None:
    b = store.get_business(suggestion.business_id)
    suggestion.channel_log.append(ChannelLog(channel="stub", at=datetime.now(timezone.utc).isoformat(), detail="stub, nothing sent"))
    suggestion.status = "sent"
    store.save_suggestion(suggestion)
    _ev("contact", b, suggestion.id, "Viesti omistajalle valmisteltu (ei lähetetty, kehitystila)",
        "Message to the owner prepared (not sent, stub)", channel="stub")


async def decide(suggestion: Suggestion) -> Decision:
    if settings.STUB_DECIDE == "wait":
        fut = asyncio.get_running_loop().create_future()
        _waiters[suggestion.id] = fut
        return await fut
    await asyncio.sleep(3)
    return Decision(suggestion_id=suggestion.id, action="approve", via="web")


def apply(suggestion: Suggestion, decision: Decision) -> ApplyResult:
    return ApplyResult(suggestion_id=suggestion.id, yext_status="stub, nothing written to Yext", publishers=[], broker_updated=False)


def learn(suggestion: Suggestion, decision: Decision) -> None:
    store.set_pref(f"last_decision:{suggestion.business_id}", decision.model_dump(mode="json"))


for _n, _f in [("detect", detect), ("suggest", suggest), ("contact", contact), ("decide", decide), ("apply", apply), ("learn", learn)]:
    _f._kaiku_stub = True
    STEPS[_n] = _f

FI_ACTION = {"approve": "hyväksytty", "edit": "muokattu", "decline": "hylätty"}
_STATUS_FOR = {"approve": "approved", "edit": "edited", "decline": "declined"}


# ---------- runner ----------
async def run_chain(business_id: str, holiday_date: str, now: Optional[datetime] = None, suggestion_id: Optional[str] = None) -> Optional[Suggestion]:
    b = store.get_business(business_id)
    if b is None:
        return None
    now = now or datetime.now(timezone.utc)
    sid = suggestion_id or ""
    gap = settings.STEP_GAP

    async def pause(step):
        if is_stub(step) and gap:
            await asyncio.sleep(gap)

    try:
        await pause("detect")
        det = await _call(STEPS["detect"], b, holiday_date, now)
        _ev("detect", b, sid, f"Tunnistettu: {holiday_date[8:]}.{holiday_date[5:7]}. voi vaatia poikkeusajat",
            f"Detected: {holiday_date[8:]}.{holiday_date[5:7]}. may need special hours", reason_codes=det.reason_codes)

        await pause("suggest")
        s = await _call(STEPS["suggest"], b, det)
        if sid:
            s.id = sid
        sid = s.id
        store.save_suggestion(s)
        _ev("suggest", b, sid, f"Ehdotus: {fmt_span(s.proposed) if s.proposed else s.kind}, varmuus {round(s.confidence * 100)} %",
            f"Suggestion: {fmt_span(s.proposed) if s.proposed else s.kind}, confidence {round(s.confidence * 100)}%",
            kind=s.kind, confidence=s.confidence, message_fi=s.message_fi, message_en=s.message_en)

        await pause("contact")
        await _call(STEPS["contact"], s)
        s = store.get_suggestion(sid) or s

        _ev("decide", b, sid, "Odotetaan omistajan päätöstä", "Waiting for the owner's decision", phase="waiting")
        dec = await _call(STEPS["decide"], s)
        s = store.get_suggestion(sid) or s
        s.status = _STATUS_FOR.get(dec.action, s.status)
        store.save_suggestion(s)
        store.save_decision(dec)
        _ev("decide", b, sid, f"Päätös: {FI_ACTION.get(dec.action, dec.action)}", f"Decision: {dec.action}", phase="decided", action=dec.action, via=dec.via)

        if dec.action != "decline":
            await pause("apply")
            res = await _call(STEPS["apply"], s, dec)
            s.status = "applied"
            store.save_suggestion(s)
            _ev("apply", b, sid, "Aukioloajat päivitetty", "Hours applied", yext_status=res.yext_status, publishers=res.publishers,
                broker_updated=res.broker_updated)
        await pause("learn")
        await _call(STEPS["learn"], s, dec)
        _ev("learn", b, sid, "Opittu seuraavaa kertaa varten", "Learned for next time", action=dec.action)
        return s
    except Exception as exc:  # the chain must never die silently
        _ev("detect" if not sid else "broker", b, sid, "Ketju pysähtyi virheeseen", "Chain stopped on an error", error=type(exc).__name__, message=str(exc)[:200])
        raise


_tasks: set[asyncio.Task] = set()


async def _bg(*a):
    try:
        await run_chain(*a)
    except Exception:
        pass


# ---------- routes ----------
@router.post("/api/run")
async def api_run(business: str = "furry-paw", date: str = "2026-12-24"):
    if store.get_business(business) is None:
        raise HTTPException(404, "unknown business")
    sid = uuid.uuid4().hex[:10]
    t = asyncio.create_task(_bg(business, date, datetime.now(timezone.utc), sid))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"suggestion_id": sid, "business": business, "date": date}


@router.get("/api/suggestions")
def api_suggestions(business: str = "furry-paw", limit: int = 20):
    return [s.model_dump(mode="json") for s in store.list_suggestions(business, limit)]


@router.get("/api/suggestions/{sid}")
def api_suggestion(sid: str):
    s = store.get_suggestion(sid)
    if not s:
        raise HTTPException(404, "not found (a run id exists before its suggestion step finishes)")
    return s.model_dump(mode="json")


@router.get("/api/business/{bid}")
def api_business(bid: str):
    b = store.get_business(bid)
    if not b:
        raise HTTPException(404, "unknown business")
    return b.model_dump(mode="json")


@router.get("/api/today")
def api_today():
    d = today()
    return {"date": d.isoformat(), "label_fi": f"Tänään: {fi_date(d)}", "label_en": f"Today: {d.isoformat()}"}


@router.post("/api/stub/decide/{sid}")
async def api_stub_decide(sid: str, action: str = "approve"):
    fut = _waiters.pop(sid, None)
    if fut is None or fut.done():
        raise HTTPException(404, "no stub decide is waiting for this id")
    fut.set_result(Decision(suggestion_id=sid, action=action, via="web"))
    return {"ok": True}
