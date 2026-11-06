"""python -m kaiku.suggest.cli --business data/furry_paw.json --date 2026-12-24 --today 2026-12-17"""
from __future__ import annotations

import argparse
import json
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--business", default="data/furry_paw.json")
    ap.add_argument("--date", required=True)
    ap.add_argument("--today", default=None)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--detection", action="store_true", help="also print the Detection")
    a = ap.parse_args(argv)
    det, sug = run(load_business(a.business), a.date, a.today, not a.no_network)
    if a.detection:
        print(json.dumps(det.to_dict(), ensure_ascii=False, indent=2))
    print(json.dumps(sug.to_dict(), ensure_ascii=False, indent=2))
    print("\n" + sug.message_fi + "\n" + sug.message_en)


if __name__ == "__main__":
    main()
