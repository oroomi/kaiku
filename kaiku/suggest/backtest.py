"""Backtest harness with a pluggable loader. python -m kaiku.suggest.backtest [path] [--jsonl out.jsonl]

JSON: {"cases": [{case, business{...}, date, today, target}]} or a bare list of the same.
CSV: columns are guessed from headers (aliases below). regular_hours may be JSON or "mon-fri 09:00-17:00; sat 10:00-14:00".
target: "closed" or "9-13" / "09:00-13:00". Fonecta's real format is unknown: add an alias or a loader, nothing else changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from kaiku.detect import holidays as hol
from kaiku.detect.engine import detect
from kaiku.suggest.engine import suggest
from kaiku.suggest.explain import hours_key
from kaiku.suggest.schema import Business

ROOT = Path(__file__).resolve().parents[2]
ALIASES = {
    "id": ["business_id", "id", "customer_id", "yritys_id"],
    "name": ["name", "business_name", "nimi", "yritys"],
    "category": ["category", "toimiala", "industry", "type"],
    "regular": ["regular_hours", "regular", "aukioloajat", "opening_hours", "hours"],
    "last_year": ["last_year", "last_year_exception", "last_year_hours", "viime_vuosi"],
    "date": ["date", "holiday_date", "paiva", "päivä"],
    "target": ["target", "target_hours", "truth", "answer", "hours_actual", "label"],
    "today": ["today", "now"],
}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def norm_hours(v):
    """'closed' | '9-13' | '09:00-13:00' | list -> 'closed' or [{'start','end'}] or None"""
    if v is None or v == "":
        return None
    if isinstance(v, list):
        return v
    t = str(v).strip().lower()
    if t in ("closed", "suljettu", "kiinni", "0", "-"):
        return "closed"
    m = re.match(r"^(\d{1,2})(?:[.:](\d{2}))?\s*-\s*(\d{1,2})(?:[.:](\d{2}))?$", t)
    if m:
        a, am, b, bm = m.groups()
        return [{"start": f"{int(a):02d}:{am or '00'}", "end": f"{int(b):02d}:{bm or '00'}"}]
    return None


def parse_regular(v):
    if isinstance(v, dict):
        return v
    if not v:
        return {}
    v = v.strip()
    if v.startswith("{"):
        return json.loads(v)
    out = {d: [] for d in DAYS}
    for part in v.split(";"):
        m = re.match(r"\s*(\w+)(?:-(\w+))?\s+(.+)", part)
        if not m:
            continue
        a, b, h = m.groups()
        a, b = a.lower()[:3], (b or a).lower()[:3]
        if a in DAYS and b in DAYS:
            for d in DAYS[DAYS.index(a):DAYS.index(b) + 1]:
                hh = norm_hours(h)
                out[d] = [] if hh == "closed" else (hh or [])
    return out


def _pick(row, key):
    for a in ALIASES[key]:
        for k in row:
            if k and k.strip().lower() == a:
                return row[k]
    return None


def load_cases(path) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
        cases = []
        for i, r in enumerate(rows):
            d = _pick(r, "date")
            ly = norm_hours(_pick(r, "last_year"))
            biz = {"id": _pick(r, "id") or f"row{i}", "name": _pick(r, "name") or f"row{i}",
                   "category": _pick(r, "category") or "shop", "regular_hours": parse_regular(_pick(r, "regular")),
                   "last_year_exceptions": []}
            h = hol.get(d)
            if ly is not None and h:
                prev = hol.same_holiday_previous_year(h)
                if prev:
                    biz["last_year_exceptions"].append({"date": prev.date, "hours": ly})
            cases.append({"case": f"{i+1}", "business": biz, "date": d, "today": _pick(r, "today"),
                          "target": _pick(r, "target")})
        return cases
    data = json.loads(p.read_text())
    return data["cases"] if isinstance(data, dict) else data


def effective(sug, det):
    """The hours the customer would end up with if they approve."""
    if sug.kind == "ask":
        return None
    if sug.kind == "closed":
        return "closed"
    if sug.kind == "hours":
        return sug.proposed
    return det.signals["regular_that_day"]["hours"] or "closed"


def run(cases, network=False):
    results = []
    for c in cases:
        b = Business.from_dict(c["business"])
        det = detect(b, c["date"], c.get("today"), use_network=network)
        s = suggest(b, det)
        eff, tgt = effective(s, det), norm_hours(c.get("target"))
        abstain = eff is None
        ok = (not abstain) and hours_key(eff) == hours_key(tgt)
        results.append({"case": c.get("case"), "business_id": b.id, "date": c["date"], "kind": s.kind,
                        "proposed": s.proposed, "confidence": s.confidence, "target": c.get("target"),
                        "abstain": abstain, "correct": ok,
                        "wrong": (not abstain) and not ok, "target_closed": hours_key(tgt) == "closed",
                        "suggestion": s.to_dict()})
    return results


def metrics(res):
    n = len(res)
    answered = [r for r in res if not r["abstain"]]
    closed = [r for r in res if r["target_closed"]]
    return {
        "cases": n,
        "exact_match_rate_all": round(sum(r["correct"] for r in res) / n, 3) if n else None,
        "exact_match_rate_answered": round(sum(r["correct"] for r in answered) / len(answered), 3) if answered else None,
        "closed_day_accuracy": round(sum(r["correct"] for r in closed) / len(closed), 3) if closed else None,
        "abstain_rate": round(sum(r["abstain"] for r in res) / n, 3) if n else None,
        "wrong_suggestion_rate": round(sum(r["wrong"] for r in res) / n, 3) if n else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "data" / "sample_cases.json"))
    ap.add_argument("--jsonl", nargs="?", const="-", default=None, metavar="PATH",
                    help="one JSON line per suggestion (for a scoring script): to stdout as a flag, or to PATH")
    ap.add_argument("--network", action="store_true")
    a = ap.parse_args(argv)
    res = run(load_cases(a.path), a.network)
    if a.jsonl == "-":
        for r in res:
            print(json.dumps(r["suggestion"], ensure_ascii=False))
        return
    if a.jsonl:
        with open(a.jsonl, "w", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(r["suggestion"], ensure_ascii=False) + "\n")
    print(f"{'case':<62} {'kind':<10} {'conf':>4}  {'target':<12} result")
    for r in res:
        out = "ASK" if r["abstain"] else ("ok" if r["correct"] else "WRONG")
        print(f"{str(r['case'])[:60]:<62} {r['kind']:<10} {r['confidence']:>4.2f}  {str(r['target']):<12} {out}")
    print(json.dumps(metrics(res), indent=1))


if __name__ == "__main__":
    main()
