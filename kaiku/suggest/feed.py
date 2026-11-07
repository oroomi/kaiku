"""The owner's first screen: "Kaiku noticed N things". Every card is a suggestion with its reason and data.

build_feed(business_id, today) -> machine-readable dict (stable field names, served at GET /api/feed/{id}).
A kind appears ONLY when real data supports it. No data, no card. Nothing here is invented.

Kinds: holiday_hours, conflict, period, no_change, description, review.
Extra loaders (description, review) are pluggable: register more with `register_loader(fn)`;
fn(business_id, today, client) -> list[card dict] and must return [] when it has no data.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from kaiku.detect import holidays as hol
from kaiku.detect.engine import detect
from kaiku.suggest import explain as ex
from kaiku.suggest import sources as src
from kaiku.suggest.engine import DS, suggest
from kaiku.suggest.schema import Business, valid_hours

WINDOW_DAYS = 45
ROOT = Path(__file__).resolve().parents[2]
# a period = holidays that belong together; the owner decides once for the whole bundle
PERIODS = [{"key": "christmas", "name_en": "Christmas period", "name_fi": "Joulun aika", "start": (12, 24), "end": (1, 6)}]
SRC_DS = {**DS, "website": DS["website"], "google": DS["google"], "lastyear": DS["lastyear"]}
SRC_NAME_EN = {"lastyear": "Last year", "website": "Your website", "google": "Google now"}
SRC_NAME_FI = {"lastyear": "Viime vuosi", "website": "Verkkosivunne", "google": "Google nyt"}


# ---------- loading ----------
def load_business(business_id: str) -> Optional[Business]:
    try:
        from kaiku import store
        b = store.get_business(business_id)
        if b is not None:
            return Business.from_dict(b.model_dump())
    except Exception:
        pass
    p = ROOT / "data" / "furry_paw.json"
    if p.exists():
        raw = json.loads(p.read_text())
        if raw.get("id") == business_id:
            raw["owner_whatsapp"] = None
            return Business.from_dict(raw)
    return None


def _as_date(x) -> date:
    if x is None:
        from kaiku.learn import timetravel
        return timetravel.today()
    return x if isinstance(x, date) else date.fromisoformat(x)


# ---------- helpers ----------
def _dm(iso: str) -> str:
    return ex.d_fi(iso)


def _reason_row(r: dict) -> dict:
    return {"source": r["source"], "dataset_id": r["dataset_id"], "text_en": r["text_en"], "text_fi": r["text_fi"]}


def _proposed(s) -> object:
    if s.kind == "closed":
        return "closed"
    return s.proposed if s.kind == "hours" else None


def _hname(s) -> tuple[str, str]:
    return (s.holiday_name_en or s.holiday_name_fi or "").strip(), (s.holiday_name_fi or s.holiday_name_en or "").strip()


def _period_of(iso: str):
    d = date.fromisoformat(iso)
    for p in PERIODS:
        sm, sd = p["start"]
        em, ed = p["end"]
        start = date(d.year, sm, sd)
        if d < start:
            start = date(d.year - 1, sm, sd)
        end = date(start.year + (1 if (em, ed) < (sm, sd) else 0), em, ed)
        if start <= d <= end:
            return p, start, end
    return None


def _source_values(det) -> list[dict]:
    """What each source says for the day. Only sources that really returned hours."""
    sg = det.signals
    out = []
    ly = sg.get("last_year") or {}
    if ly.get("found"):
        out.append({"source": "lastyear", "value": ly["hours"], "note": f"on {_dm(ly['date'])} last year"})
    ws = sg.get("website")
    if ws and ws.get("hours") is not None:
        out.append({"source": "website", "value": ws["hours"], "note": ws.get("quote")})
    g = sg.get("google_now") or {}
    if g.get("status") == "shows_hours" and g.get("hours") is not None:
        out.append({"source": "google", "value": g["hours"], "note": g.get("text")})
    return out


_TIME_RANGE = re.compile(r"\b(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\b")


def _short_times(text: str) -> str:
    """'09:00-13:00' -> '9-13', '09:30-17:00' -> '9:30-17' (the demo writes times as 9-13)."""
    def one(m):
        a = f"{int(m.group(1))}" + ("" if m.group(2) == "00" else ":" + m.group(2))
        b = f"{int(m.group(3))}" + ("" if m.group(4) == "00" else ":" + m.group(4))
        return f"{a}-{b}"
    return _TIME_RANGE.sub(one, text or "")


def _hshort(hours) -> str:
    return _short_times(ex.hours_en(hours))


def _chat_text(msg: str, en: str, d: str, prop_short: str) -> str:
    """The chat bubble form of a WhatsApp message: no greeting, short times, 'I suggest 9-13.' at the end,
    and it starts with the card title so the chat does not repeat it."""
    t = re.sub(r"^Hi [^!.]*[!.]\s*", "", msg or "")
    if en:
        t = re.sub(r"^%s is on (\w+) %s" % (re.escape(en), re.escape(d)), lambda m: f"{en} {d} is a {m.group(1)}.", t)
    t = re.sub(r"\s*We suggest:.*$", f" I suggest {prop_short}.", t)
    return _short_times(t).strip()


def _holiday_card(b: Business, s, det) -> dict:
    en, fi = _hname(s)
    d = _dm(s.holiday_date)
    prop_en = _hshort(_proposed(s))
    return {"id": f"feed-{b.id}-holiday_hours-{s.holiday_date}", "kind": "holiday_hours",
            "title_en": f"{en or 'Holiday'} {d}", "text_en": _chat_text(s.message_en, en, d, prop_en),
            "title_fi": f"{fi or 'Pyhä'} {d}: {ex.hours_fi(_proposed(s))}", "text_fi": s.message_fi,
            "proposed": _proposed(s), "confidence": s.confidence,
            "reasons": [_reason_row(r) for r in s.reasons], "status": "proposed", "holiday_date": s.holiday_date,
            "suggestion_id": s.id}


def _conflict_card(b: Business, s, det, vals) -> dict:
    d = _dm(s.holiday_date)
    reasons = []
    for v in vals:
        reasons.append({"source": v["source"], "dataset_id": SRC_DS[v["source"]],
                        "text_en": f"{SRC_NAME_EN[v['source']]}: {ex.hours_en(v['value'])}" + (f" ({v['note']})" if v.get("note") else ""),
                        "text_fi": f"{SRC_NAME_FI[v['source']]}: {ex.hours_fi(v['value'])}"})
    listing_en = "; ".join(f"{SRC_NAME_EN[v['source']].lower()} says {ex.hours_en(v['value'])}" for v in vals)
    prop = _proposed(s)
    return {"id": f"feed-{b.id}-conflict-{s.holiday_date}", "kind": "conflict",
            "title_en": f"Your sources disagree about {d}", "title_fi": f"Lähteenne ovat eri mieltä päivästä {d}",
            "text_en": f"{listing_en.capitalize()}. I suggest {ex.hours_en(prop)}. Please confirm.",
            "text_fi": f"Lähteet kertovat eri aukioloajat päivälle {d}. Ehdotan: {ex.hours_fi(prop)}. Vahvistatko?",
            "proposed": prop, "confidence": s.confidence, "reasons": reasons, "status": "proposed",
            "holiday_date": s.holiday_date,
            "sources": [{"source": v["source"], "dataset_id": SRC_DS[v["source"]], "value": v["value"]} for v in vals]}


def _no_change_card(b: Business, s) -> dict:
    en, fi = _hname(s)
    d = _dm(s.holiday_date)
    return {"id": f"feed-{b.id}-no_change-{s.holiday_date}", "kind": "no_change",
            "title_en": f"{en} {d}: no change needed", "title_fi": f"{fi} {d}: ei muutosta",
            "text_en": _short_times(re.sub(r"^Hi [^!.]*[!.]\s*", "", s.message_en or "")), "text_fi": s.message_fi,
            "proposed": None, "confidence": s.confidence,
            "reasons": [_reason_row(r) for r in s.reasons], "status": "info", "holiday_date": s.holiday_date}


def _period_card(b: Business, p, start: date, end: date, items: list, permitted: bool) -> dict:
    dates = []
    for s in items:
        en, fi = _hname(s)
        dates.append({"date": s.holiday_date, "name_en": en, "name_fi": fi, "kind": s.kind,
                      "proposed": _proposed(s), "confidence": s.confidence})
    n = len(dates)
    lines_en = "; ".join(f"{_dm(x['date'])} {_hshort(x['proposed']) if x['kind'] != 'no_change' else 'no change'}" for x in dates)
    lines_fi = "; ".join(f"{_dm(x['date'])} {ex.hours_fi(x['proposed']) if x['kind'] != 'no_change' else 'ei muutosta'}" for x in dates)
    ask_en = "Want me to handle this period every year?"
    reasons = [_reason_row(r) for s in items for r in s.reasons[:1]]
    return {"id": f"feed-{b.id}-period-{p['key']}-{start.year}", "kind": "period",
            "title_en": f"{p['name_en']}: {n} dates", "title_fi": f"{p['name_fi']}: {n} päivää",
            "text_en": f"I suggest {lines_en}. {ask_en}" if not permitted else f"I suggest {lines_en}.",
            "text_fi": f"{lines_fi}. Hoidanko tämän jakson puolestasi joka vuosi?" if not permitted else f"{lines_fi}.",
            "proposed": dates, "confidence": round(min(x["confidence"] for x in dates), 4), "reasons": reasons,
            "status": "proposed", "period": {"key": p["key"], "start": start.isoformat(), "end": end.isoformat()},
            "holiday_date": dates[0]["date"], "standing_permission_offered": not permitted,
            "standing_permission_text_en": ask_en}


# ---------- pluggable loaders (Yext entity, reviews). Return [] without real data ----------
def _yext_client():
    from kaiku.apply.yext import YextSandbox
    return YextSandbox()


def _owner_lang(business_id: str) -> str:
    try:
        from kaiku import store
        b = store.get_business(business_id)
        return "fi" if b is not None and getattr(b, "owner_language", "en") == "fi" else "en"
    except Exception:
        return "en"


def _short_hash(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode()).hexdigest()[:6]


def _sample_reason() -> dict:
    return {"source": "sample", "dataset_id": "urn:kaiku:src:sample", "text_en": src.SAMPLE_NOTE_EN, "text_fi": src.SAMPLE_NOTE_FI}


def description_loader(business_id: str, today: date, client) -> list[dict]:
    """Yext entity description: missing -> a draft by Kaiku; present -> typos (word list first, then the brain)."""
    eid = _entity_id(business_id)
    ent = client.get_entity(eid)
    desc = (ent.get("description") or "").strip()
    ds = "urn:kaiku:src:yext:description"
    if not desc:
        name = ent.get("name") or business_id
        addr = ent.get("address") or {}
        address = ", ".join(x for x in (addr.get("line1"), addr.get("city")) if x) or "address not given"
        cat = ent.get("categories") or {}
        cat_txt = ", ".join(str(v) for vs in cat.values() for v in (vs if isinstance(vs, list) else [vs]))
        text, by_brain = src.draft_description(name, cat_txt, address, src.hours_summary(ent.get("hours") or {}))
        return [{"id": f"feed-{business_id}-description-missing", "kind": "description",
                 "title_en": "Your listing has no description", "title_fi": "Listauksessanne ei ole kuvausta",
                 "text_en": f"Customers see no description of {name}. Here is a draft you could publish (draft by Kaiku): \"{text}\"",
                 "text_fi": f"{name} ei näy kuvausta asiakkaille. Tässä Kaikun luonnos (luonnos: Kaiku): \"{text}\"",
                 "proposed": text, "confidence": 0.6, "holiday_date": None, "status": "proposed", "entity_id": eid,
                 "reasons": [{"source": "yext", "dataset_id": ds, "text_en": "The Yext entity has no description field",
                              "text_fi": "Yext-kohteella ei ole kuvauskenttää"},
                             {"source": "kaiku_draft", "dataset_id": "urn:kaiku:src:kaiku:draft",
                              "text_en": "draft by Kaiku from your name, category, address and opening hours" + ("" if by_brain else " (template)"),
                              "text_fi": "Kaikun luonnos nimestä, kategoriasta, osoitteesta ja aukioloajoista"}]}]
    typos = src.find_typos(desc)
    if not typos:
        return []
    fixed = src.apply_typos(desc, typos)
    if fixed == desc:
        return []
    shown = typos[:3]
    quoted_en = "; ".join(f'"{t["wrong"]}" should be "{t["right"]}"' for t in shown)
    quoted_fi = "; ".join(f'"{t["wrong"]}" pitäisi olla "{t["right"]}"' for t in shown)
    reasons = [{"source": "yext", "dataset_id": ds, "text_en": f"Yext entity description: \"{src.quote(desc, 120)}\"",
                "text_fi": f"Yextin kuvaus: \"{src.quote(desc, 120)}\""}]
    if src.is_sample_description(desc):
        reasons.append(_sample_reason())
    return [{"id": f"feed-{business_id}-description-typo-{_short_hash(desc)}", "kind": "description",
             "title_en": "Typo in your description", "title_fi": "Kirjoitusvirhe yrityskuvauksessanne",
             "text_en": f"{quoted_en}. Shall I fix it?", "text_fi": f"{quoted_fi}. Korjaanko sen?",
             "proposed": fixed, "confidence": 0.9, "holiday_date": None, "status": "proposed", "entity_id": eid,
             "typos": shown, "reasons": reasons}]


def _replied(rid: str) -> bool:
    from kaiku.apply.yext import reply_log_path
    p = reply_log_path()
    try:
        return p.exists() and any(json.loads(l).get("review_id") == rid for l in p.read_text().splitlines() if l.strip())
    except (OSError, ValueError):
        return False


def _sample_reviews() -> list[dict]:
    p = ROOT / "data" / "furry_paw_reviews_sample.json"
    return json.loads(p.read_text()).get("reviews", []) if p.exists() else []


def review_loader(business_id: str, today: date, client, limit: int = 3) -> list[dict]:
    """Unanswered reviews, 3 stars or less first, quoted verbatim. Reads the Yext Reviews API; when the sandbox has none,
    the team's labelled sample file is used and every card says so."""
    eid = _entity_id(business_id)
    reviews, from_sample = [], False
    try:
        reviews = client.list_reviews(eid)
    except Exception:
        reviews = []
    if not reviews:
        reviews, from_sample = _sample_reviews(), True
    lang = _owner_lang(business_id)
    name = "the business"
    try:
        name = client.get_entity(eid).get("name") or name
    except Exception:
        pass
    open_ = []
    for r in reviews:
        rating, text = r.get("rating"), (r.get("content") or r.get("comment") or "").strip()
        rid = str(r.get("id") or r.get("reviewId") or "")
        if rating is None or not text or not rid or r.get("comments") or r.get("response") or _replied(rid):
            continue
        open_.append((int(round(float(rating))), text, rid, r))
    open_.sort(key=lambda x: (x[0] > 3, x[0]))
    cards = []
    for rating, text, rid, r in open_[:limit]:
        reply, by_brain = src.draft_reply(rating, text, name, lang)
        sample = from_sample or src.is_sample_review(r)
        reasons = [{"source": "sample_reviews" if from_sample else "yext_reviews",
                    "dataset_id": "urn:kaiku:src:sample:reviews" if from_sample else "urn:kaiku:src:yext:reviews",
                    "text_en": f"Review {rid}, {rating} stars, no reply yet" + (" (file: data/furry_paw_reviews_sample.json)" if from_sample else ""),
                    "text_fi": f"Arvostelu {rid}, {rating} tähteä, ei vastausta"},
                   {"source": "kaiku_draft", "dataset_id": "urn:kaiku:src:kaiku:draft",
                    "text_en": "reply drafted by Kaiku" + ("" if by_brain else " (template)") + ", for you to approve or change",
                    "text_fi": "Kaikun luonnostelema vastaus, hyväksyttävänä tai muokattavana"}]
        if sample:
            reasons.append(_sample_reason())
        q = src.quote(text)
        cards.append({"id": f"feed-{business_id}-review-{rid}", "kind": "review", "review_id": rid, "entity_id": eid,
                      "rating": rating, "author": r.get("authorName"),
                      "title_en": f"A {rating}-star review has no reply", "title_fi": f"{rating} tähden arvostelu ilman vastausta",
                      "text_en": f"\"{q}\" Here is a reply you could post:", "text_fi": f"\"{q}\" Tässä vastaus, jonka voisit julkaista:",
                      "proposed": reply, "confidence": 0.7, "holiday_date": None, "status": "proposed", "reasons": reasons})
    return cards


def _entity_id(business_id: str) -> str:
    try:
        from kaiku.chain import ENTITY
        return ENTITY
    except Exception:
        return "SinceAI07"


LOADERS: list[Callable] = [description_loader, review_loader]


def register_loader(fn: Callable) -> None:
    LOADERS.append(fn)


# ---------- main ----------
def build_feed(business_id: str, today=None, use_network: bool = True, extra_loaders: bool = True) -> dict:
    t = _as_date(today)
    b = load_business(business_id)
    out = {"business_id": business_id, "today": t.isoformat(), "suggestions": []}
    if b is None:
        out["error"] = "unknown business"
        return out
    try:
        from kaiku.learn import prefs
        permitted = bool(prefs.get_prefs(business_id).get("standing_permission"))
    except Exception:
        permitted = False
    cards: list[dict] = []
    period_items: dict = {}
    for h in hol.upcoming(t, WINDOW_DAYS):
        det = detect(b, h.date, t, use_network=use_network)
        s = suggest(b, det)
        if s.status == "expired" or s.kind == "ask":
            continue  # past dates and "not enough data" are not feed cards; the ask goes through the chain
        if s.kind == "no_change":
            cards.append(_no_change_card(b, s))
            continue
        per = _period_of(h.date)
        vals = _source_values(det)
        if len({ex.hours_key(v["value"]) for v in vals}) > 1:
            cards.append(_conflict_card(b, s, det, vals))
        if per:
            period_items.setdefault((per[0]["key"], per[1]), (per, []))[1].append(s)
        else:
            cards.append(_holiday_card(b, s, det))
    for _, (per, items) in period_items.items():
        # the nearest date of the period is also its own card, so the owner can act on it today
        cards.append(_holiday_card(b, items[0], None))
        if len(items) >= 2:
            cards.append(_period_card(b, per[0], per[1], per[2], items, permitted))
    if extra_loaders and use_network:
        try:
            client = _yext_client()
        except Exception:
            client = None
        if client is not None:
            for fn in LOADERS:
                try:
                    cards.extend(fn(business_id, t, client))
                except Exception:
                    continue  # a loader without data or access adds nothing
    order = {"conflict": 0, "holiday_hours": 1, "period": 2, "review": 3, "description": 4, "no_change": 5}
    cards.sort(key=lambda c: (c.get("holiday_date") or "9999", order.get(c["kind"], 9)))
    out["suggestions"] = cards
    out["count"] = len(cards)
    return out
