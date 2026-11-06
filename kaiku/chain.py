"""The chain: detect > suggest > contact > decide(wait) > apply > learn.

Other modules register real implementations at import time with `chain.register("detect", fn)`.
Until they land, the stubs below produce plausible output from the seed so the UI works.
Step functions may be sync or async.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
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
log = logging.getLogger("kaiku.chain")
STUB_DECIDE_DELAY = 3.0  # seconds before the stub decide auto-approves


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
        d = store.get_pref("today", settings.DEMO_TODAY)
        return date.fromisoformat(d)


def now_dt() -> datetime:
    try:
        from .learn import timetravel  # type: ignore
        return timetravel.now()
    except Exception:
        return datetime.now(timezone.utc)


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
    await asyncio.sleep(STUB_DECIDE_DELAY)
    return Decision(suggestion_id=suggestion.id, action="approve", via="web")


def apply(suggestion: Suggestion, decision: Decision) -> ApplyResult:
    return ApplyResult(suggestion_id=suggestion.id, yext_status="stub, nothing written to Yext", publishers=[], broker_updated=False)


def learn(suggestion: Suggestion, decision: Decision) -> None:
    store.set_pref(f"last_decision:{suggestion.business_id}", decision.model_dump(mode="json"))


for _n, _f in [("detect", detect), ("suggest", suggest), ("contact", contact), ("decide", decide), ("apply", apply), ("learn", learn)]:
    _f._kaiku_stub = True
    STEPS[_n] = _f

FI_ACTION = {"approve": "hyväksytty", "edit": "muokattu", "decline": "hylätty", "timeout": "ei vastausta"}
_STATUS_FOR = {"approve": "approved", "edit": "edited", "decline": "declined"}
ENTITY = settings.YEXT_ENTITY_ID


# ---------- adapters for the real modules (pydantic contracts <-> the builders' dataclasses) ----------
def _sbiz(b: Business):
    from .suggest.schema import Business as SB
    return SB.from_dict(b.model_dump(mode="json"))


def _real_detect(business: Business, holiday_date: str, now: datetime) -> Detection:
    from .detect.engine import detect as d
    # shim: detect._as_date keeps a datetime as is (datetime is a date subclass) and then fails comparing it to a date
    det = d(_sbiz(business), holiday_date, now.date() if isinstance(now, datetime) else now)
    return Detection(business_id=det.business_id, holiday_date=det.holiday_date, signals=det.signals,
                     reason_codes=det.reason_codes, holiday=det.holiday, status=getattr(det, "status", "ok"))


def _real_suggest(business: Business, detection: Detection) -> Suggestion:
    from .suggest.engine import suggest as sg
    from .suggest.schema import Detection as SD
    sd = SD(business_id=detection.business_id, holiday_date=detection.holiday_date, signals=detection.signals,
            reason_codes=detection.reason_codes, holiday=detection.holiday, status=detection.status)
    out = sg(_sbiz(business), sd).to_dict()
    out["decide_url"] = None
    return Suggestion.model_validate(out)


def _apply_prefs(s: Suggestion) -> Suggestion:
    """Learned preferences (edits, declines, standing permission) adjust the suggestion before contact."""
    try:
        from .learn import prefs
    except Exception:
        return s
    d = s.model_dump(mode="json")
    new = prefs.apply_prefs(s.business_id, d)
    for k in ("kind", "proposed", "confidence", "auto_apply", "auto_apply_reason_fi"):
        if k in new:
            d[k] = new[k]
    if new.get("reason_fi"):
        d["reasons"].append({"source": "learn", "dataset_id": "", "text_fi": new["reason_fi"],
                             "text_en": new.get("reason_en") or new["reason_fi"]})
        if new.get("learned_from_edit") or new.get("suppressed"):
            d["message_fi"] = (d["message_fi"] + " " + new["reason_fi"]).strip()
            d["message_en"] = (d["message_en"] + " " + (new.get("reason_en") or "")).strip()
    return Suggestion.model_validate(d)


def whatsapp_configured() -> bool:
    try:
        from .contact import whatsapp
        return bool(whatsapp.get_client().configured)
    except Exception:
        return False


def decide_link(s: Suggestion) -> str:
    try:
        from .decide import tokens
        return tokens.link_for(s.id, s.business_id)
    except Exception:
        return settings.PUBLIC_URL.rstrip("/") + "/d/" + s.id  # placeholder until the decide module is merged


def contact_message(s: Suggestion) -> str:
    try:
        from .contact import messages
        return messages.suggestion_text(s.model_dump(mode="json"))
    except Exception:
        return s.message_fi


async def contact_step(s: Suggestion) -> None:
    """WhatsApp first. Without WA_TOKEN the lane is degraded: no message leaves, the decision link is shown instead."""
    b = store.get_business(s.business_id)
    msg = contact_message(s)
    if whatsapp_configured():
        from .contact import ladder
        d = s.model_dump(mode="json")
        await asyncio.to_thread(ladder.contact, d)  # ladder emits its own contact events
        s.channel_log = [ChannelLog(**c) for c in d.get("channel_log", [])]
        s.status = d.get("status", s.status)
    else:
        now = datetime.now(timezone.utc).isoformat()
        s.channel_log.append(ChannelLog(channel="whatsapp", at=now, detail="BLOCKED: WA_TOKEN not set"))
        s.channel_log.append(ChannelLog(channel="call", at=now, detail="call lane not configured"))
        s.status = "sent"
        if s.kind == "no_change":  # informational only: there is nothing to decide
            _ev("contact", b, s.id, "WhatsApp ei ole vielä käytössä, tiedotus valmis (ei muutosta)",
                "WhatsApp not configured yet, notice ready (no change)", message_fi=msg, degraded=True)
        else:
            _ev("contact", b, s.id, "WhatsApp ei ole vielä käytössä, päätöslinkki valmis",
                "WhatsApp not configured yet, decision link ready", decide_url=s.decide_url, message_fi=msg, degraded=True)
    store.save_suggestion(s)


async def on_decision(decision) -> bool:
    """Entry point for decisions made outside the chain (WhatsApp webhook, call). Resolves whichever decide step waits."""
    d = decision if isinstance(decision, dict) else decision.model_dump(mode="json")
    sid = d.get("suggestion_id", "")
    try:
        from . import decide
        if decide.resolve(sid, d):
            return True
    except Exception:
        pass
    fut = _waiters.pop(sid, None)
    if fut is not None and not fut.done():
        fut.set_result(Decision(**{k: v for k, v in d.items() if k in Decision.model_fields}))
        return True
    return False


# ---------- broker (the spine). Never lets a failure stop the chain ----------
def get_broker():
    from .broker import get_broker as g
    return g()


def _hours_json(proposed):
    return "closed" if proposed in (None, "closed") else [s if isinstance(s, dict) else s.model_dump() for s in proposed]


def _entity(b: Business, status: str = "missing", day: str = ""):
    from .broker import models as M
    mb = M.Business(id=b.id, name=b.name, address=b.address, city=b.city, lat=b.lat, lon=b.lon, category=b.category,
                    regular_hours={k: [s.model_dump() for s in v] for k, v in b.regular_hours.items()},
                    website=b.website or "", source=b.source)
    return M, M.business_to_entity(mb, status={"date": day, "status": status})


def broker_seed(business_id: str = "furry-paw", fresh: bool = False) -> str:
    """Create the Furry Paw entity with holidayHoursStatus present. fresh=True replaces it (demo reset)."""
    b = store.get_business(business_id)
    br = get_broker()
    M, ent = _entity(b)
    if fresh:
        br.delete_entity(ent["id"])  # fallback upsert merges, Orion replaces: delete first so both start clean
    if fresh or br.get_entity(ent["id"]) is None:
        br.upsert_entity(ent)
    return br.name


def broker_set(b: Business, what: str, day: str, proposed=None, status: str = "") -> str:
    """what: 'status' | 'proposed' | 'truth'. Returns the backend name."""
    br = get_broker()
    M, ent = _entity(b)
    eid = ent["id"]
    if br.get_entity(eid) is None:
        br.upsert_entity(ent)
    if what == "proposed":
        br.append_instance(eid, "holidayHours", M.hours_value(day, _hours_json(proposed)), "proposed")
    elif what == "truth":
        br.set_default(eid, "holidayHours", M.hours_value(day, _hours_json(proposed)))
    if status:
        br.set_default(eid, "holidayHoursStatus", {"date": day, "status": status})
    return br.name


async def _broker(b: Business, sid: str, fi: str, en: str, **kw) -> bool:
    try:
        name = await asyncio.to_thread(broker_set, b, **kw)
        _ev("broker", b, sid, fi + ("" if name == "orion-ld" else " (varakäsittelijä)"),
            en + ("" if name == "orion-ld" else " (fallback broker)"), broker=name, what=kw.get("what"), status=kw.get("status"))
        return True
    except Exception as exc:
        log.warning("broker write failed: %s", exc)
        _ev("broker", b, sid, "Broker ei vastaa, ketju jatkuu", "Broker offline, the chain continues", message=str(exc)[:120])
        return False


# ---------- apply (real Yext sandbox write) ----------
def apply_backend(entity_id: str, day: str, proposed) -> dict:
    from .apply import apply_suggestion
    return apply_suggestion(entity_id, day, proposed)


def _hours_to_write(s: Suggestion, dec: Decision):
    if dec.action == "edit" and dec.edited is not None:
        return "closed" if dec.edited == "closed" else [x.model_dump() if hasattr(x, "model_dump") else x for x in dec.edited]
    if s.kind == "closed":
        return "closed"
    if s.kind == "hours" and s.proposed:
        return [x.model_dump() for x in s.proposed]
    return None


def apply_real(s: Suggestion, dec: Decision) -> tuple[ApplyResult, dict]:
    hours = _hours_to_write(s, dec)
    if hours is None:
        return ApplyResult(suggestion_id=s.id, yext_status="nothing to write"), {"written": None}
    out = apply_backend(ENTITY, s.holiday_date, hours)
    try:
        from .apply.publishers import publishers_for
        pubs = publishers_for()
    except Exception:
        pubs = []
    out["where_it_shows"] = pubs
    out["hours"] = hours
    res = ApplyResult(suggestion_id=s.id, yext_status=out.get("yext_status", "?"), publishers=[p["name"] for p in pubs])
    return res, out


def _s_dict(s: Suggestion) -> dict:
    d = s.model_dump(mode="json")
    d["holiday"] = {"name_fi": s.holiday_name_fi, "name_en": s.holiday_name_en}
    return d


def learn_real(s: Suggestion, dec: Decision) -> dict:
    from .learn import prefs
    return prefs.record_decision(s.business_id, _s_dict(s), dec.model_dump(mode="json"))


def _learn_text(s: Suggestion, dec: Decision, p: dict) -> tuple[str, str, dict]:
    from .learn import prefs
    hid = prefs.holiday_id(_s_dict(s))
    if dec.action == "edit":
        return (f"Opittu: {hid} aukeaa jatkossa {prefs._hours_fi(dec.edited)}", f"Learned: {hid} will use {prefs._hours_en(dec.edited)} next time", {"holiday": hid})
    if dec.action == "decline":
        n = (p.get("declines", {}).get(hid) or {}).get("count", 1)
        return (f"Opittu: ehdotus {hid} hylättiin ({n}. kerta)", f"Learned: suggestion for {hid} declined (time {n})", {"holiday": hid, "declines": n})
    extra = "; pysyvä lupa annettu" if dec.standing_permission else ""
    extra_en = "; standing permission granted" if dec.standing_permission else ""
    return (f"Opittu: {hid} hyväksytty{extra}, sama ehdotus kelpaa jatkossa", f"Learned: {hid} approved{extra_en}, the same suggestion will do next time",
            {"holiday": hid, "standing_permission": bool(dec.standing_permission)})


async def _apply_step(s, dec):
    return await asyncio.to_thread(apply_real, s, dec)


async def _learn_step(s, dec):
    try:
        return await asyncio.to_thread(learn_real, s, dec)
    except Exception as exc:
        log.warning("learn failed: %s", exc)
        return {}


def _install_real_steps() -> None:
    """Replace the stubs with the builders' engines. Each import is guarded: a missing module keeps its stub."""
    async def detect_step(b, d, now):
        return await asyncio.to_thread(_real_detect, b, d, now)

    async def suggest_step(b, det):
        return await asyncio.to_thread(_real_suggest, b, det)
    try:
        from .detect import engine  # noqa: F401
        from .suggest import engine as _e  # noqa: F401
        register("detect", detect_step)
        register("suggest", suggest_step)
    except Exception as exc:
        log.warning("real detect/suggest unavailable: %s", exc)
    register("contact", contact_step)
    try:
        from .apply import apply_suggestion  # noqa: F401
        register("apply", _apply_step)
    except Exception as exc:
        log.warning("real apply unavailable (stub stays): %s", exc)
    try:
        from .learn import prefs  # noqa: F401
        register("learn", _learn_step)
    except Exception as exc:
        log.warning("real learn unavailable (stub stays): %s", exc)


_install_real_steps()


# ---------- runner ----------
def _short(d: str) -> str:
    return f"{int(d[8:10])}.{int(d[5:7])}."


async def run_chain(business_id: str, holiday_date: str, now: Optional[datetime] = None, suggestion_id: Optional[str] = None) -> Optional[Suggestion]:
    b = store.get_business(business_id)
    if b is None:
        return None
    now = now or now_dt()
    sid = suggestion_id or ""
    gap = settings.STEP_GAP

    async def pause(step):
        if is_stub(step) and gap:
            await asyncio.sleep(gap)

    day = _short(holiday_date)
    try:
        await _broker(b, sid, f"Brokerin tila: {day} aukioloajat puuttuvat", f"Broker status: {day} hours missing",
                      what="status", day=holiday_date, status="missing")
        await pause("detect")
        det = await _call(STEPS["detect"], b, holiday_date, now)
        hn = (det.holiday or {}).get("name_fi")
        _ev("detect", b, sid, f"Tunnistettu: {day} ({hn}) voi vaatia poikkeusajat" if hn else f"Tunnistettu: {day} voi vaatia poikkeusajat",
            f"Detected: {day} may need special hours", reason_codes=det.reason_codes, holiday=det.holiday, signals=det.signals)

        await pause("suggest")
        s = await _call(STEPS["suggest"], b, det)
        if sid:
            s.id = sid
        sid = s.id
        s = _apply_prefs(s)
        s.decide_url = decide_link(s)
        store.save_suggestion(s)
        what_fi = fmt_span(s.proposed) if s.proposed else {"closed": "suljettu", "no_change": "ei muutosta", "ask": "kysytään omistajalta"}.get(s.kind, s.kind)
        what_en = fmt_span(s.proposed) if s.proposed else {"closed": "closed", "no_change": "no change", "ask": "ask the owner"}.get(s.kind, s.kind)
        _ev("suggest", b, sid, f"Ehdotus: {what_fi}, varmuus {round(s.confidence * 100)} %",
            f"Suggestion: {what_en}, confidence {round(s.confidence * 100)}%",
            kind=s.kind, confidence=s.confidence, message_fi=s.message_fi, message_en=s.message_en,
            reasons=[r.model_dump() for r in s.reasons], proposed=[x.model_dump() for x in s.proposed] if s.proposed else None)
        if s.kind in ("hours", "closed"):
            await _broker(b, sid, f"Ehdotus kirjattu brokeriin ({day}, datasetId proposed)", f"Proposal written to the broker ({day}, datasetId proposed)",
                          what="proposed", day=holiday_date, proposed=s.proposed or "closed", status="proposed")

        await pause("contact")
        await _call(STEPS["contact"], s)
        s = store.get_suggestion(sid) or s

        if s.kind == "no_change":
            _ev("decide", b, sid, "Päätöstä ei tarvita, ei muutosta", "No decision needed, no change", phase="skipped")
            _ev("apply", b, sid, "Ei kirjoitettu, aukioloajat pysyvät ennallaan", "Nothing written, the hours stay as they are", written=None, skipped=True)
            _ev("learn", b, sid, "Ei opittavaa tällä kertaa", "Nothing to learn this time", skipped=True)
            return s

        _ev("decide", b, sid, "Odotetaan omistajan päätöstä", "Waiting for the owner's decision", phase="waiting", decide_url=s.decide_url)
        dec = await _call(STEPS["decide"], s)
        s = store.get_suggestion(sid) or s
        if dec.action == "timeout":
            _ev("decide", b, sid, "Omistaja ei vastannut, mitään ei muutettu", "The owner did not answer, nothing was changed", phase="timeout")
            return s
        s.status = _STATUS_FOR.get(dec.action, s.status)
        store.save_suggestion(s)
        store.save_decision(dec)
        _ev("decide", b, sid, f"Päätös: {FI_ACTION.get(dec.action, dec.action)}", f"Decision: {dec.action}", phase="decided", action=dec.action, via=dec.via)

        if dec.action != "decline":
            await pause("apply")
            r = await _call(STEPS["apply"], s, dec)
            res, out = r if isinstance(r, tuple) else (r, {})
            ok = res.yext_status == "ok"
            verified = out.get("verified")
            if ok:
                s.status = "applied"
                store.save_suggestion(s)
                res.broker_updated = await _broker(b, sid, f"Päätös kirjattu brokeriin ({day}, oletusinstanssi)",
                                                   f"Decision written to the broker as the default instance ({day})",
                                                   what="truth", day=holiday_date, proposed=out.get("hours") or _hours_to_write(s, dec), status="applied")
            _ev("apply", b, sid,
                f"Aukioloajat tallennettu Yextiin ({day}), luettu takaisin" if ok and verified else
                (f"Aukioloajat päivitetty ({day})" if ok else "Yext-kirjoitus epäonnistui"),
                f"Hours saved to Yext ({day}), read back and verified" if ok and verified else
                (f"Hours applied ({day})" if ok else "Yext write failed"),
                yext_status=res.yext_status, verified=verified, entity=out.get("entity_id"), written=out.get("written"),
                entity_version=out.get("entity_version"), environment=out.get("environment"), publishers=res.publishers,
                where_it_shows=out.get("where_it_shows", []), broker_updated=res.broker_updated, error=(res.yext_status if not ok else None))
            if ok and whatsapp_configured():
                try:
                    from .contact import ladder, router as cr
                    phone = ladder.owner_phone(_s_dict(s))
                    if phone:
                        await asyncio.to_thread(cr.send_receipt, phone, {**res.model_dump(), "holiday_name_fi": s.holiday_name_fi,
                                                                         "holiday_name_en": s.holiday_name_en, "hours": out.get("hours")})
                except Exception as exc:
                    log.warning("receipt failed: %s", exc)
        await pause("learn")
        p = await _call(STEPS["learn"], s, dec)
        try:
            fi, en, det_ = _learn_text(s, dec, p if isinstance(p, dict) else {})
        except Exception:
            fi, en, det_ = "Opittu seuraavaa kertaa varten", "Learned for next time", {}
        _ev("learn", b, sid, fi, en, action=dec.action, **det_)
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
    t = asyncio.create_task(_bg(business, date, now_dt(), sid))
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


def voice_available() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("kaiku.voice") is not None
    except Exception:
        return False


def status_dict() -> dict:
    try:
        broker = get_broker().name
    except Exception:
        broker = "fallback"
    return {"broker": broker, "whatsapp_configured": whatsapp_configured(), "yext_entity": ENTITY,
            "today": today().isoformat(), "public_url": settings.PUBLIC_URL, "voice": voice_available()}


@router.get("/api/status")
def api_status():
    return status_dict()


def yext_reset() -> dict:
    from .apply.yext import YextSandbox
    return YextSandbox().reset_demo(ENTITY)


@router.post("/api/reset")
async def api_reset(learn: int = 0):
    """Demo reset: zero holiday rows on the sandbox, no suggestions or events, broker back to 'missing', clock 2026-12-17."""
    for t in list(_tasks):
        t.cancel()
    out: dict = {}
    try:
        hrs = await asyncio.to_thread(yext_reset)
        out["yext_holiday_rows"] = len(hrs.get("holidayHours", []))
    except Exception as exc:
        out["yext_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    out.update(store.clear_runs("furry-paw"))
    try:
        await asyncio.to_thread(broker_seed, "furry-paw", True)
        out["broker_reset"] = True
    except Exception as exc:
        out["broker_reset"] = False
        log.warning("broker reset failed: %s", exc)
    try:
        from .learn import timetravel, prefs
        timetravel.set_today(date.fromisoformat(settings.DEMO_TODAY))
        if learn:
            prefs.write_json_atomic(prefs._file(), {})
    except Exception as exc:
        store.set_pref("today", settings.DEMO_TODAY)
        log.warning("timetravel reset failed: %s", exc)
    return {**status_dict(), "reset": out}
