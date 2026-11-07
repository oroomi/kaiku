"""In-memory dataset reader for /eval. Same column guessing as kaiku.suggest.backtest.load_cases, plus an explicit,
overridable column mapping, JSON lists of businesses with a holidays/dates list, and per-row error reporting.
Nothing is written to disk."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

from kaiku.detect import holidays as hol
from kaiku.suggest import backtest as bt

FIELDS = ["id", "name", "category", "regular", "last_year", "date", "target", "today"]
FIELD_HELP = {"id": "business id", "name": "business name", "category": "category", "regular": "regular hours",
              "last_year": "last year's hours", "date": "holiday date", "target": "expected hours (target)",
              "today": "today (fake clock)"}
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500


class LoadError(ValueError):
    def __init__(self, msg, headers=None, mapping=None):
        super().__init__(msg)
        self.headers, self.mapping = headers or [], mapping or {}


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise LoadError("The file is not readable text (expected UTF-8 CSV or JSON).")


def norm_date(v):
    if v is None:
        return None
    t = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", t):
        t = t[:10]
    else:
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", t)
        if m:
            t = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    try:
        return date.fromisoformat(t).isoformat()
    except ValueError:
        return None


def guess_mapping(headers: list[str]) -> dict:
    """field -> header name (as written in the file) or None, by backtest.ALIASES."""
    out = {}
    low = {(h or "").strip().lower(): h for h in headers}
    for f in FIELDS:
        out[f] = next((low[a] for a in bt.ALIASES[f] if a in low), None)
    return out


def _flat_to_case(row: dict, i: int, mapping: dict) -> dict:
    def pick(f):
        h = mapping.get(f)
        return row.get(h) if h else None
    d_raw = pick("date")
    d = norm_date(d_raw)
    ly = bt.norm_hours(pick("last_year"))
    reg = pick("regular")
    err = None
    try:
        regular = bt.parse_regular(reg)
    except (ValueError, TypeError) as e:
        regular, err = {}, f"regular hours not readable ({e})"
    biz = {"id": pick("id") or f"row{i}", "name": pick("name") or f"row{i}", "category": pick("category") or "shop",
           "regular_hours": regular, "last_year_exceptions": []}
    for k in ("website", "city", "address"):
        if row.get(k):
            biz[k] = row[k]
    h = hol.get(d) if d else None
    if ly is not None and h:
        prev = hol.same_holiday_previous_year(h)
        if prev:
            biz["last_year_exceptions"].append({"date": prev.date, "hours": ly})
    if d is None:
        err = err or f"date {d_raw!r} not understood (use 2026-12-24 or 24.12.2026)"
    return {"case": f"{i + 1}", "business": biz, "date": d, "today": norm_date(pick("today")), "target": pick("target"),
            "_error": err}


def _sniff(text: str) -> str:
    first = text.splitlines()[0] if text.strip() else ""
    return max([",", ";", "\t"], key=first.count)


def parse(raw: bytes, filename: str = "", mapping_override: dict | None = None):
    """-> (cases, info). info = {kind, headers, mapping, note}. Raises LoadError with a plain-words message."""
    if len(raw) > MAX_BYTES:
        raise LoadError("The file is larger than 2 MB. Send a smaller sample (500 rows at most).")
    text = decode(raw)
    if not text.strip():
        raise LoadError("The file is empty.")
    is_json = text.lstrip()[:1] in "[{" or filename.lower().endswith(".json")
    if is_json:
        cases, info = _parse_json(text, mapping_override)
    else:
        cases, info = _parse_csv(text, mapping_override)
    if not cases:
        raise LoadError("No rows found in the file.", info.get("headers"), info.get("mapping"))
    if len(cases) > MAX_ROWS:
        raise LoadError(f"The file has {len(cases)} rows; the limit is {MAX_ROWS}. Send a smaller sample.")
    return cases, info


def _parse_csv(text, override):
    try:
        rdr = csv.DictReader(io.StringIO(text), delimiter=_sniff(text))
        headers = [h for h in (rdr.fieldnames or []) if h]
        rows = list(rdr)
    except csv.Error as e:
        raise LoadError(f"The CSV could not be read: {e}.")
    if not headers:
        raise LoadError("No header row found. The first line must name the columns.")
    mapping = guess_mapping(headers)
    for k, v in (override or {}).items():
        if k in FIELDS:
            if v and v not in headers:
                raise LoadError(f"Column {v!r} is not in the file. Columns: {', '.join(headers)}.", headers, mapping)
            mapping[k] = v or None
    if not mapping["date"]:
        raise LoadError("No date column found. Choose which column holds the holiday date.", headers, mapping)
    cases = [_flat_to_case(r, i, mapping) for i, r in enumerate(rows) if any((v or "").strip() for v in r.values() if isinstance(v, str))]
    return cases, {"kind": "csv", "headers": headers, "mapping": mapping, "delimiter": _sniff(text)}


def _parse_json(text, override):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LoadError(f"The JSON could not be parsed: {e.msg} at line {e.lineno}, column {e.colno}.")
    if isinstance(data, dict):
        if isinstance(data.get("cases"), list):
            data = data["cases"]
        elif isinstance(data.get("businesses"), list):
            data = data["businesses"]
        else:
            raise LoadError('The JSON object must have a "cases" list (or be a list of businesses).')
    if not isinstance(data, list):
        raise LoadError("The JSON must be a list of cases or businesses.")
    if not all(isinstance(x, dict) for x in data):
        raise LoadError("Every item in the JSON list must be an object.")
    if any("business" in x for x in data):
        cases = []
        for i, x in enumerate(data):
            if not isinstance(x.get("business"), dict):
                cases.append({"case": str(x.get("case", i + 1)), "business": {"id": f"row{i}", "name": f"row{i}"}, "date": None,
                              "today": None, "target": None, "_error": 'item has no "business" object'})
                continue
            d = norm_date(x.get("date"))
            cases.append({"case": str(x.get("case", i + 1)), "business": x["business"], "date": d,
                          "today": norm_date(x.get("today")), "target": x.get("target"),
                          "_error": None if d else f"date {x.get('date')!r} not understood"})
        return cases, {"kind": "json-cases", "headers": [], "mapping": {},
                       "note": "Nested cases: business, date, today and target are read from their own keys."}
    if any(("holidays" in x or "dates" in x) for x in data):
        cases = []
        for i, x in enumerate(data):
            ds = x.get("holidays", x.get("dates")) or []
            if isinstance(ds, (str, dict)):
                ds = [ds]
            biz = {k: v for k, v in x.items() if k not in ("holidays", "dates", "target")}
            biz.setdefault("id", f"biz{i + 1}")
            biz.setdefault("name", biz["id"])
            if isinstance(biz.get("regular_hours"), str):
                try:
                    biz["regular_hours"] = bt.parse_regular(biz["regular_hours"])
                except (ValueError, TypeError):
                    biz["regular_hours"] = {}
            for j, dd in enumerate(ds):
                tgt = None
                if isinstance(dd, dict):
                    tgt, dd = dd.get("target"), dd.get("date")
                d = norm_date(dd)
                cases.append({"case": f"{biz['name']} {d or dd}", "business": biz, "date": d, "today": None, "target": tgt,
                              "_error": None if d else f"date {dd!r} not understood"})
        return cases, {"kind": "json-businesses", "headers": [], "mapping": {},
                       "note": 'A list of businesses: one case per entry of its "holidays" / "dates" list.'}
    # flat rows in JSON: same as CSV
    headers = []
    for x in data:
        for k in x:
            if k not in headers:
                headers.append(k)
    mapping = guess_mapping(headers)
    for k, v in (override or {}).items():
        if k in FIELDS:
            mapping[k] = v if v in headers else None
    if not mapping["date"]:
        raise LoadError('No date found. Give each item a "date" (or "holidays": [...] for a business), or choose the field.',
                        headers, mapping)
    return [_flat_to_case(r, i, mapping) for i, r in enumerate(data)], {"kind": "json-flat", "headers": headers, "mapping": mapping}
