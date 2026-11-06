"""POST /webhooks/call: ElevenLabs post-call webhook -> Decision (via "call") -> chain, like a WhatsApp tap."""
from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request

from . import call as C
from . import whatsapp as W

router = APIRouter()  # defined before importing .router, which includes this router (circular import)

from . import router as R  # noqa: E402
TOLERANCE_S = 30 * 60

# ------------------------------------------------------------------ signature

def sign(secret: str, body: bytes, t: int | None = None) -> str:
    """Header value 'ElevenLabs-Signature: t=<unix>,v0=<hex hmac-sha256 of "<t>.<body>">'."""
    t = int(t if t is not None else time.time())
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v0={mac}"


def signature_ok(secret: str, body: bytes, header: str | None, now: float | None = None) -> bool:
    if not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        t = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - t) > TOLERANCE_S:
        return False
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, parts.get("v0", ""))


# ------------------------------------------------------------------ Finnish transcript parser

_ELA = {"yhdestä": 1, "kahdesta": 2, "kolmesta": 3, "neljästä": 4, "viidestä": 5, "kuudesta": 6, "seitsemästä": 7,
        "kahdeksasta": 8, "yhdeksästä": 9, "kymmenestä": 10, "yhdestätoista": 11, "kahdestatoista": 12,
        "kolmestatoista": 13, "neljästätoista": 14, "viidestätoista": 15, "kuudestatoista": 16,
        "seitsemästätoista": 17, "kahdeksastatoista": 18}
_ILL = {"yhteen": 1, "kahteen": 2, "kolmeen": 3, "neljään": 4, "viiteen": 5, "kuuteen": 6, "seitsemään": 7,
        "kahdeksaan": 8, "yhdeksään": 9, "kymmeneen": 10, "yhteentoista": 11, "kahteentoista": 12,
        "kolmeentoista": 13, "neljääntoista": 14, "viiteentoista": 15, "kuuteentoista": 16,
        "seitsemääntoista": 17, "kahdeksaantoista": 18}
_NOM = {"yksi": 1, "kaksi": 2, "kolme": 3, "neljä": 4, "viisi": 5, "kuusi": 6, "seitsemän": 7, "kahdeksan": 8,
        "yhdeksän": 9, "kymmenen": 10, "yksitoista": 11, "kaksitoista": 12}

_NUM = r"(\d{1,2})(?:[:.](\d{2}))?"
_DIGITS = re.compile(rf"(?:klo\.?\s*)?{_NUM}\s*(?:-|–|—|to|alkaen|ja)\s*(?:klo\.?\s*)?{_NUM}")
_WORDS = re.compile(r"\b(" + "|".join(sorted(_ELA, key=len, reverse=True)) + r")\s+(?:klo\s+)?(" +
                    "|".join(sorted(_ILL, key=len, reverse=True)) + r")(?:\s+asti)?\b")
_WORDS_NOM = re.compile(r"\b(" + "|".join(sorted(_NOM, key=len, reverse=True)) + r")\s+(" +
                        "|".join(sorted(_ILL, key=len, reverse=True)) + r")\b")
_CLOSED = re.compile(r"\b(suljettu|suljemme|kiinni|ei ole auki|ollaan kiinni|olemme kiinni|closed)\b")
_DECLINE = re.compile(r"\b(ei|en|ei kiitos|älä muuta|ei muutosta|ei halua)\b")
_APPROVE = re.compile(r"\b(kyllä|kylla|joo|juu|jees|hyväksyn|hyväksytään|selvä|sopii|okei|ok|oikein|just niin|voit päivittää)\b")


def _hhmm(h: int, m: str | None) -> str | None:
    mi = int(m or 0)
    if not (0 <= h <= 24 and 0 <= mi < 60):
        return None
    return f"{h:02d}:{mi:02d}"


def _span(a: int, b: int) -> list[dict] | None:
    if b <= a and b < 12:  # "yhdeksästä yhteen" -> 9-13
        b += 12
    x, y = _hhmm(a, None), _hhmm(b, None)
    return [{"start": x, "end": y}] if x and y and x < y else None


def parse_hours(text: str):
    """-> 'closed' | [{'start','end'}] | None, from a free Finnish phrase or 'HH:MM-HH:MM'."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if t == "closed" or _CLOSED.search(t):
        return "closed"
    m = _DIGITS.search(t)
    if m:
        a, b = _hhmm(int(m[1]), m[2]), _hhmm(int(m[3]), m[4])
        if a and b:
            if b <= a and int(m[3]) < 12 and not m[4]:
                b = _hhmm(int(m[3]) + 12, None)
            if b and a < b:
                return [{"start": a, "end": b}]
    m = _WORDS.search(t)
    if m:
        return _span(_ELA[m[1]], _ILL[m[2]])
    m = _WORDS_NOM.search(t)
    if m:
        return _span(_NOM[m[1]], _ILL[m[2]])
    return None


def parse_utterance(text: str) -> dict | None:
    """-> {'action':'approve'} | {'action':'decline'} | {'action':'edit','edited':...} | None"""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not t:
        return None
    h = parse_hours(t)
    if h is not None:
        return {"action": "edit", "edited": h}
    if _DECLINE.search(t) and not _APPROVE.search(t):
        return {"action": "decline"}
    if _APPROVE.search(t) and not re.search(r"\bei\b", t):
        return {"action": "approve"}
    return None


def parse_transcript(transcript: list[dict]) -> dict | None:
    """Last owner turn that says something decisive, only after the agent has asked 'Hyväksytkö'."""
    turns = [(x.get("role"), x.get("message") or "") for x in transcript or []]
    start = 0
    for i, (role, msg) in enumerate(turns):
        if role == "agent" and "hyväksyt" in msg.lower():
            start = i + 1
            break
    for role, msg in reversed(turns[start:]):
        if role == "user":
            d = parse_utterance(msg)
            if d:
                return d
    return None


def from_analysis(analysis: dict) -> dict | None:
    dc = (analysis or {}).get("data_collection_results") or {}

    def val(k):
        v = dc.get(k)
        return (v.get("value") if isinstance(v, dict) else v) or None
    act = str(val("action") or "").strip().lower()
    if act == "approve":
        return {"action": "approve"}
    if act == "decline":
        return {"action": "decline"}
    if act == "edit":
        h = parse_hours(str(val("hours") or ""))
        return {"action": "edit", "edited": h} if h is not None else None
    return None


def derive(data: dict) -> dict | None:
    return from_analysis(data.get("analysis") or {}) or parse_transcript(data.get("transcript") or [])


# ------------------------------------------------------------------ handling

def _ids(data: dict) -> tuple[str | None, str | None]:
    ci = data.get("conversation_initiation_client_data") or {}
    dv = ci.get("dynamic_variables") or {}
    sid = dv.get("suggestion_id") or ci.get("user_id") or (data.get("metadata") or {}).get("user_id") or data.get("user_id")
    biz = dv.get("business_id")
    if not sid:
        rec = C.suggestion_for_conversation(data.get("conversation_id", ""))
        sid, biz = rec.get("suggestion_id"), biz or rec.get("business_id")
    return sid, biz


def _emit(sid, biz, fi, en, detail=None, step="decide"):
    try:
        from kaiku import events  # type: ignore
        events.emit(events.Event(ts=C._now(), step=step, business_id=biz, suggestion_id=sid,
                                 title_fi=fi, title_en=en, detail=detail or {}))
    except Exception:
        pass


async def _forward(decision: dict) -> bool:
    try:
        from kaiku import chain  # type: ignore
        fn = getattr(chain, "on_decision", None)
        if fn:
            r = fn(decision)
            return bool(await r if inspect.isawaitable(r) else r)
    except Exception:
        pass
    try:
        from kaiku import decide  # type: ignore
        return bool(decide.resolve(decision["suggestion_id"], decision))
    except Exception:
        return False


async def handle_payload(payload: dict) -> dict:
    typ = payload.get("type", "")
    data = payload.get("data") or {}
    sid, biz = _ids(data)
    if typ == "call_initiation_failure":
        why = data.get("failure_reason", "unknown")
        _emit(sid, biz, "Puhelu: omistaja ei vastannut", "Call: the owner did not answer", {"reason": why}, step="contact")
        return {"ok": True, "handled": "failure", "reason": why}
    if typ and typ != "post_call_transcription":
        return {"ok": True, "ignored": typ}
    if not sid:
        return {"ok": True, "ignored": "unknown suggestion"}
    d = derive(data)
    if not d:
        _emit(sid, biz, "Puhelu: päätöstä ei saatu", "Call: no decision reached", {"conversation_id": data.get("conversation_id")})
        return {"ok": True, "decision": None}
    decision = R.make_decision(sid, d["action"], d.get("edited"), via="call")
    with R._lock:
        st = R._load()
        if sid in st["decided"]:
            return {"ok": True, "decision": None, "ignored": "already decided"}
        st["decided"][sid] = decision["action"]
        R._save(st)
    fi = {"approve": "Puhelu: omistaja hyväksyi", "edit": "Puhelu: omistaja antoi muut ajat",
          "decline": "Puhelu: omistaja kieltäytyi"}[decision["action"]]
    en = {"approve": "Call: the owner approved", "edit": "Call: the owner gave other hours",
          "decline": "Call: the owner declined"}[decision["action"]]
    _emit(sid, biz, fi, en, {"decision": decision})
    _emit(sid, biz, fi, en, {"decision": decision}, step="contact")
    accepted = await _forward(decision)
    return {"ok": True, "decision": decision, "accepted": accepted}


@router.post("/webhooks/call")
async def inbound(request: Request):
    raw = await request.body()
    W.load_env()
    secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET")
    if secret and not signature_ok(secret, raw, request.headers.get("elevenlabs-signature")):
        raise HTTPException(401, "bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "bad json")
    res = await handle_payload(payload)
    return {"ok": True, "decision": (res.get("decision") or {}).get("action")}
