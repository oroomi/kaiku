"""Deterministic fallback: yes / no / hours, so the chat works even when the LLM call fails."""
from __future__ import annotations

import re

from ..contact.router import parse_free_text

_YES = {"yes do it", "yes please", "yes please do", "i agree", "agree", "agreed", "approve it", "approve this", "sounds right",
        "that is right", "thats right", "that's right", "correct", "yes that works", "yes that is fine", "ok do it", "okay do it",
        "yes every year", "yes always", "always", "every year", "every time", "yes each year"}
_NO = {"no thank you", "no thanks", "not this time", "no not now", "no dont", "no don't", "never mind", "nevermind", "cancel"}
_CHANGE = {"change the hours", "change hours", "edit", "edit the hours", "change", "change it", "different hours", "other hours"}
_LEAD = re.compile(r"^(?:please\s+)?(?:make it|set it to|set it|change it to|change to|change them to|let's do|lets do|use|do|put|"
                   r"it should be|should be|how about|actually|rather|instead)\s+", re.I)


def normalize(text: str) -> str:
    t = (text or "").strip().lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"[!?]+", "", t)
    t = re.sub(r"[,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t


def parse(text: str) -> dict | None:
    """-> {'action':'approve'|'decline'|'change'} | {'action':'edit','edited':...} | None."""
    t = normalize(text)
    if not t:
        return None
    if t in _CHANGE:
        return {"action": "change"}
    if t in _YES:
        return {"action": "approve"}
    if t in _NO:
        return {"action": "decline"}
    for cand in (t, _LEAD.sub("", t)):
        r = parse_free_text(cand)
        if r:
            return r
    # "yes make it 10-14" / "ok but 10-14"
    m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|to|until)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*$", t)
    if m:
        return parse_free_text(m.group(1))
    return None
