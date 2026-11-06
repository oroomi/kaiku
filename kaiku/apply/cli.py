"""python -m kaiku.apply.cli show|set-holiday DATE START END|set-closed DATE|remove DATE|revert FILE"""
from __future__ import annotations

import argparse
import json
import sys

from kaiku.apply.yext import YextError, YextSandbox, apply_suggestion

ENTITY = "SinceAI07"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kaiku.apply.cli")
    ap.add_argument("--entity", default=ENTITY)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("set-holiday"); p.add_argument("date"); p.add_argument("start"); p.add_argument("end")
    sub.add_parser("set-closed").add_argument("date")
    sub.add_parser("remove").add_argument("date")
    sub.add_parser("revert").add_argument("file")
    a = ap.parse_args(argv)
    try:
        c = YextSandbox()
        if a.cmd == "show":
            res = c.get_hours(a.entity)
        elif a.cmd == "set-holiday":
            res = apply_suggestion(a.entity, a.date, [{"start": a.start, "end": a.end}], c)
        elif a.cmd == "set-closed":
            res = apply_suggestion(a.entity, a.date, "closed", c)
        elif a.cmd == "remove":
            c.snapshot(a.entity); c.remove_holiday_hours(a.entity, a.date); res = c.get_hours(a.entity)
        else:
            c.revert(a.entity, a.file); res = c.get_hours(a.entity)
    except YextError as e:
        print(f"error: {e}", file=sys.stderr); return 1
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if not (isinstance(res, dict) and str(res.get("yext_status", "ok")).startswith("error")) else 1


if __name__ == "__main__":
    sys.exit(main())
