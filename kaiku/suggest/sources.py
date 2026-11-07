"""Text sources for the feed: business description (typos, missing) and review replies.

Pure helpers + small brain calls. Every brain call is optional: no key, a timeout or bad JSON gives the deterministic
fallback, never an invented fact. Nothing here writes to Yext (kaiku.apply.yext does, after the owner approves).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

MODEL = "claude-sonnet-5-5"
CACHE_TTL = 600.0
_cache: dict = {}

SAMPLE_DESC_MARK = "Sample text written by team VY7"
SAMPLE_REVIEW_AUTHOR = "Sample reviewer"
SAMPLE_NOTE_EN = "source: sample description/reviews written by the team (the Yext sandbox entity has none of its own)"
SAMPLE_NOTE_FI = "lähde: tiimin kirjoittama näyteteksti (Yextin hiekkalaatikossa ei ole omaa)"

# ---------- deterministic typo pass ----------
MISSPELLINGS = {
    "vacination": "vaccination", "vacinations": "vaccinations", "vaccinaton": "vaccination", "vaccination's": "vaccinations",
    "recieve": "receive", "adress": "address", "apointment": "appointment", "appointmnet": "appointment",
    "appoinment": "appointment", "apointments": "appointments", "teh": "the", "occured": "occurred",
    "seperate": "separate", "definately": "definitely", "accomodate": "accommodate", "wich": "which",
    "becuase": "because", "untill": "until", "enviroment": "environment", "sugery": "surgery", "surgey": "surgery",
    "clinc": "clinic", "vetinary": "veterinary", "veterinarian's": "veterinarians", "dentel": "dental", "xrays": "X-rays",
    "emergancy": "emergency", "emmergency": "emergency", "avaliable": "available", "availible": "available",
    "servises": "services", "servce": "service", "oppening": "opening", "oppen": "open", "hoursr": "hours",
}
_ABBREV = ("e.g", "i.e", "etc", "vs", "dr", "st", "no")


def _match_case(wrong: str, right: str) -> str:
    if wrong.isupper() and len(wrong) > 1:
        return right.upper()
    if wrong[:1].isupper():
        return right[:1].upper() + right[1:]
    return right


def deterministic_typos(text: str) -> list[dict]:
    """[{wrong, right}] found by a small word list, double spaces and a lower-case sentence start."""
    out, seen = [], set()

    def add(w, r):
        if w != r and w not in seen:
            seen.add(w)
            out.append({"wrong": w, "right": r})
    for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        w = m.group(0)
        r = MISSPELLINGS.get(w.lower())
        if r:
            add(w, _match_case(w, r))
    for m in re.finditer(r"(\S+)( {2,})(\S+)", text):
        add(m.group(0), f"{m.group(1)} {m.group(3)}")
    first = text.lstrip()[:1]
    if first.islower():
        w = re.match(r"\S+", text.lstrip()).group(0)
        add(w, w[:1].upper() + w[1:])
    for m in re.finditer(r"([.!?])\s+([a-z]\w*)", text):
        before = text[:m.start(1)].split()[-1:] or [""]
        if before[0].lower().rstrip(".") in _ABBREV or re.fullmatch(r"[A-Za-z]", before[0]):
            continue
        w = m.group(2)
        add(f"{m.group(1)} {w}", f"{m.group(1)} {w[:1].upper()}{w[1:]}")
    return out


def apply_typos(text: str, typos: list[dict]) -> str:
    """The corrected FULL text. Each wrong string is replaced where it stands; double spaces are collapsed last."""
    for t in typos:
        w, r = t["wrong"], t["right"]
        if re.fullmatch(r"[A-Za-z][A-Za-z']*", w):
            text = re.sub(rf"(?<![A-Za-z']){re.escape(w)}(?![A-Za-z'])", r, text)
        else:
            text = text.replace(w, r)
    return re.sub(r"(?<=\S) {2,}(?=\S)", " ", text)


def _clean(s: str) -> str:
    return s.replace("—", ",").replace("–", "-").strip()


# ---------- brain (optional) ----------
def _api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and not os.environ.get("KAIKU_CHAT_NO_LLM")


def _complete(system: str, user: str, max_tokens: int = 400) -> str | None:
    if not _api_key():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(max_retries=1, timeout=20.0)
        r = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                   messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip() or None
    except Exception:
        return None


def _cached(key: str, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def clear_cache() -> None:
    _cache.clear()


def llm_typos(text: str) -> list[dict]:
    """Brain pass in strict JSON, cached 10 min; any failure gives []."""
    def run():
        raw = _complete(
            "You proofread a small business's public description. Find ONLY clear spelling mistakes and typos "
            "(not style, not wording, not names, not Finnish place names). Reply with JSON only: "
            '{"typos":[{"wrong":"<exact substring of the text>","right":"<correction>"}]}. No typos: {"typos":[]}.',
            text, 300)
        if not raw:
            return []
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            items = json.loads(m.group(0)).get("typos", []) if m else []
        except (ValueError, AttributeError):
            return []
        good = []
        for t in items if isinstance(items, list) else []:
            if isinstance(t, dict) and isinstance(t.get("wrong"), str) and isinstance(t.get("right"), str):
                w, r = t["wrong"].strip(), t["right"].strip()
                if w and r and w != r and w in text and len(w) <= 60 and len(r) <= 60:
                    good.append({"wrong": w, "right": r})
        return good[:5]
    return _cached("typos:" + hashlib.sha1(text.encode()).hexdigest(), run)


def find_typos(text: str) -> list[dict]:
    typos = deterministic_typos(text)
    have = {t["wrong"] for t in typos}
    for t in llm_typos(text):
        if t["wrong"] not in have:
            typos.append(t)
    return typos


# ---------- drafts ----------
def hours_summary(hours: dict) -> str:
    """'Mon-Fri 9-17, Sat 10-14, Sun closed' from a Yext hours object; '' when unknown."""
    names = [("monday", "Mon"), ("tuesday", "Tue"), ("wednesday", "Wed"), ("thursday", "Thu"), ("friday", "Fri"),
             ("saturday", "Sat"), ("sunday", "Sun")]
    parts = []
    for key, nm in names:
        d = (hours or {}).get(key) or {}
        if d.get("isClosed"):
            parts.append((nm, "closed"))
        elif d.get("openIntervals"):
            parts.append((nm, ", ".join(f"{int(i['start'][:2])}{'' if i['start'][3:] == '00' else ':' + i['start'][3:]}"
                                        f"-{int(i['end'][:2])}{'' if i['end'][3:] == '00' else ':' + i['end'][3:]}"
                                        for i in d["openIntervals"])))
    out, i = [], 0
    while i < len(parts):
        j = i
        while j + 1 < len(parts) and parts[j + 1][1] == parts[i][1]:
            j += 1
        out.append(f"{parts[i][0]}{'-' + parts[j][0] if j > i else ''} {parts[i][1]}")
        i = j + 1
    return ", ".join(out)


def draft_description(name: str, category: str, address: str, hours_txt: str) -> tuple[str, bool]:
    """-> (text, by_brain). Built from the listing's own facts only."""
    def run():
        t = _complete(
            "Write a public business description of 2 sentences, at most 45 words, plain and factual, for a local "
            "business listing. Use ONLY the facts given. No claims about quality, prices, awards or services that are "
            "not given. No emoji, no dashes as punctuation. Reply with the description only.",
            f"Name: {name}\nCategory: {category or 'not given'}\nAddress: {address}\nOpening hours: {hours_txt or 'not given'}", 200)
        return _clean(t) if t else None
    t = _cached("desc:" + name + address + hours_txt, run)
    if t:
        return t, True
    base = f"{name} is a local business at {address}."
    return (base + (f" Open {hours_txt}." if hours_txt else "")), False


def reply_fallback(rating: int, text: str, lang: str = "en") -> str:
    if lang == "fi":
        if rating >= 4:
            return "Kiitos ystävällisestä palautteesta! Mukava kuulla, että asiointi sujui hyvin."
        return ("Kiitos palautteesta ja pahoittelut odotuksesta. Otamme palautteen vakavasti ja käymme sen läpi "
                "tiimin kanssa. Olet tervetullut ottamaan yhteyttä, niin selvitämme asian.")
    if rating >= 4:
        return "Thank you for the kind words! We are glad we could help, and we hope to see you and your pet again."
    return ("Thank you for your feedback, and we are sorry about the experience. We take it seriously and will go "
            "through it with the team. You are welcome to contact us so we can look into it together.")


def draft_reply(rating: int, text: str, name: str, lang: str = "en") -> tuple[str, bool]:
    """-> (reply, by_brain). <= 60 words, warm, no promises, no discounts."""
    def run():
        t = _complete(
            f"You write the business owner's public reply to a customer review for {name}. At most 60 words, warm and "
            f"calm, in {'Finnish' if lang == 'fi' else 'English'}. Thank them, acknowledge what they said. Do NOT promise "
            "anything, offer no discounts, refunds or compensation, do not invent facts or names, no emoji, no dashes "
            "as punctuation. Reply with the reply text only.",
            f"{rating} star review: {text}", 220)
        if not t:
            return None
        t = _clean(t)
        return t if 0 < len(t.split()) <= 60 else None
    t = _cached(f"reply:{lang}:{rating}:{text}", run)
    if t:
        return t, True
    return reply_fallback(rating, text, lang), False


def quote(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def is_sample_description(text: str) -> bool:
    return SAMPLE_DESC_MARK in (text or "")


def is_sample_review(r: dict) -> bool:
    return str(r.get("authorName") or "").startswith(SAMPLE_REVIEW_AUTHOR) or str(r.get("id", "")).startswith("sample-")
