"""Runs the suggest engine over parsed cases with backtest.run (network off) and shapes per-row results."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from kaiku.detect import holidays as hol
from kaiku.detect import signals as sg
from kaiku.suggest import backtest as bt
from kaiku.suggest.engine import ASK_BELOW
from kaiku.suggest.explain import hours_key
from kaiku.suggest.schema import Business, Holiday

TIME_LIMIT = 20.0
SAMPLE = Path(bt.ROOT) / "data" / "sample_cases.json"


class TooSlow(RuntimeError):
    pass


def _prime_holidays():
    """Use the bundled holiday table; never refresh it from Nager.Date inside an eval run."""
    if hol._cache is None:
        data = hol._load_bundled()
        if data is None:
            data = [h for y in (2025, 2026, 2027) for h in hol.flag_days(y)]
        hol._cache = [Holiday(**h) for h in data]


def flat(hours) -> str:
    if hours is None:
        return ""
    if hours == "closed" or hours == []:
        return "closed"
    return ", ".join(f"{x['start']}-{x['end']}" for x in hours)


def _answer(r, c):
    """(plain answer, flat hours or '') for one result."""
    k = r["kind"]
    if k == "ask":
        return "Ask the owner", ""
    if k == "closed":
        return "Closed", "closed"
    if k == "hours":
        return "Open " + flat(r["proposed"]), flat(r["proposed"])
    b = Business.from_dict(c["business"])
    reg = sg.regular_that_day(b, c["date"])["hours"]
    fh = flat(reg or "closed")
    return "No change (" + ("closed as usual" if fh == "closed" else "open as usual " + fh) + ")", fh


def run_cases(cases, deadline: float | None = None):
    deadline = TIME_LIMIT if deadline is None else deadline
    _prime_holidays()
    t0 = time.monotonic()
    rows, ok = [], []
    for c in cases:
        if time.monotonic() - t0 > deadline:
            raise TooSlow(f"The run took longer than {int(deadline)} seconds and was stopped. Send fewer rows.")
        biz = c.get("business") or {}
        base = {"case": c.get("case"), "business": biz.get("name") or biz.get("id") or "?", "date": c.get("date"),
                "target": c.get("target") if c.get("target") not in (None, "") else None}
        if c.get("_error"):
            rows.append(dict(base, status="error", error=c["_error"]))
            continue
        try:
            r = bt.run([{k: v for k, v in c.items() if k != "_error"}], network=False)[0]
        except Exception as e:  # noqa: BLE001  a bad row never breaks the run
            rows.append(dict(base, status="error", error=f"could not run this row ({type(e).__name__}: {e})"))
            continue
        tgt = bt.norm_hours(c.get("target"))
        answer, fl = _answer(r, c)
        s = r["suggestion"]
        status = "no_target" if tgt is None else ("ask" if r["abstain"] else ("match" if r["correct"] else "miss"))
        h = (s.get("holiday_name_en") or s.get("holiday_name_fi") or "")
        rows.append(dict(base, status=status, kind=r["kind"], answer=answer, hours_flat=fl,
                         confidence=r["confidence"], holiday=h or "not a listed holiday", target_flat=flat(tgt) if tgt is not None else "",
                         reasons=[x.get("text_en") for x in s.get("reasons", []) if x.get("text_en")],
                         low_confidence=r["confidence"] < ASK_BELOW and r["kind"] != "ask",
                         suggestion=s))
        if tgt is not None:
            ok.append(r)
    scored = [r for r in ok]
    allres = [r for r in rows if r["status"] != "error"]
    m = bt.metrics(scored) if scored else None
    summary = {
        "rows": len(rows), "rows_run": len(allres), "rows_with_error": len(rows) - len(allres),
        "rows_scored": len(scored), "has_target": bool(scored),
        "metrics": m,
        "ask_rate_all_rows": round(sum(r["kind"] == "ask" for r in allres) / len(allres), 3) if allres else None,
        "ask_below": ASK_BELOW,
        "always_answer": os.environ.get("KAIKU_EVAL_ALWAYS_ANSWER") == "1",
        "matches": sum(r["status"] == "match" for r in rows), "misses": sum(r["status"] == "miss" for r in rows),
        "asks": sum(r["kind"] == "ask" for r in allres),
    }
    return rows, summary


_sample_cache: dict = {}


def sample_result():
    """The 10 sample cases, run once per answer mode and kept in memory."""
    mode = os.environ.get("KAIKU_EVAL_ALWAYS_ANSWER") == "1"
    if mode not in _sample_cache:
        data = json.loads(SAMPLE.read_text())
        rows, summary = run_cases(bt.load_cases(SAMPLE))
        _sample_cache[mode] = {"ok": True, "rows": rows, "summary": summary, "kind": "json-cases", "headers": [],
                               "mapping": {}, "title": data.get("_label"),
                               "note": "Nested cases: business, date, today and target are read from their own keys.",
                               "label": "Our own 10 sample cases, written by the team; not Fonecta's data."}
    return _sample_cache[mode]
