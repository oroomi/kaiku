"""python -m kaiku.suggest.cli --business data/furry_paw.json --date 2026-12-24 --today 2026-12-17 [--jsonl]

Exit codes: 0 ok, 2 invalid input (one line on stderr, no traceback)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from kaiku.detect.engine import detect
from kaiku.suggest.engine import suggest
from kaiku.suggest.schema import Business

ROOT = Path(__file__).resolve().parents[2]


def load_business(path: str) -> Business:
    p = Path(path)
    if not p.exists():  # core's seed may not be merged yet: fall back to our own sample copy
        cases = json.loads((ROOT / "data" / "sample_cases.json").read_text())["cases"]
        return Business.from_dict(cases[0]["business"])
    return Business.from_dict(json.loads(p.read_text()))


def run(business: Business, date: str, today: str, network: bool = True):
    det = detect(business, date, today, use_network=network)
    return det, suggest(business, det)


def _fail(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def _iso(value: str, what: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        _fail(f"invalid {what} {value!r}, expected YYYY-MM-DD")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--business", default="data/furry_paw.json")
    ap.add_argument("--date", required=True, nargs="+")
    ap.add_argument("--today", default=None)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--detection", action="store_true", help="also print the Detection")
    ap.add_argument("--jsonl", nargs="?", const="-", default=None, metavar="PATH",
                    help="print one Suggestion per line (JSON) to stdout, or to PATH when given")
    a = ap.parse_args(argv)
    dates = [_iso(d, "date") for d in a.date]
    today = _iso(a.today, "today") if a.today else None
    try:
        business = load_business(a.business)
    except (OSError, ValueError, TypeError) as e:
        _fail(f"cannot read business {a.business!r}: {e}")
    out = []
    for d in dates:
        det, sug = run(business, d, today, not a.no_network)
        out.append((det, sug))
    if a.jsonl is not None:
        lines = [json.dumps(s.to_dict(), ensure_ascii=False) for _, s in out]
        if a.jsonl == "-":
            print("\n".join(lines))
        else:
            Path(a.jsonl).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    for det, sug in out:
        if det.status == "past":
            print(f"PAST: {sug.holiday_date} is before today ({today}). No suggestion is made.")
        if a.detection:
            print(json.dumps(det.to_dict(), ensure_ascii=False, indent=2))
        print(json.dumps(sug.to_dict(), ensure_ascii=False, indent=2))
        print("\n" + sug.message_fi + "\n" + sug.message_en)
    return 0


if __name__ == "__main__":
    sys.exit(main())
