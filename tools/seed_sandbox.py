"""Seed the Yext sandbox entity with the labelled SAMPLE description and two SAMPLE first-party reviews. Idempotent.

Run:  python tools/seed_sandbox.py           (env: YEXT_API_KEY, optional YEXT_ENTITY_ID)
The sandbox entity has no description and no reviews; Fonecta provisioned it empty. Everything written here is
sample text written by the team and says so. If the key cannot create reviews, data/furry_paw_reviews_sample.json is used.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kaiku.apply.yext import YextError, YextSandbox  # noqa: E402

DESC = ROOT / "data" / "furry_paw_description_sample.txt"
REVIEWS = ROOT / "data" / "furry_paw_reviews_sample.json"
AUTHOR = "Sample reviewer (fictional)"
SAMPLES = [(5, "Kind staff, quick help for our cat."),
           (3, "Waited 40 minutes for a booked appointment. Staff were kind though.")]


def seed(entity_id: str | None = None, client: YextSandbox | None = None, say=print) -> dict:
    eid = entity_id or os.environ.get("YEXT_ENTITY_ID", "SinceAI07")
    c = client or YextSandbox()
    out: dict = {"entity": eid}
    text = DESC.read_text().strip()
    cur = c.get_description(eid)
    if cur == text:
        out["description"] = "already present"
    else:
        c.set_description(eid, text)
        out["description"] = "written and read back"
    say(f"description: {out['description']}")
    try:
        have = {(r.get("rating"), (r.get("content") or "").strip()) for r in c.list_reviews(eid)}
        made = []
        for rating, content in SAMPLES:
            if (rating, content) in have:
                continue
            made.append(c.create_review(eid, AUTHOR, content, rating))
        out["reviews"] = f"created {made}" if made else "already present"
        out["reviews_api"] = "ok"
    except YextError as e:
        out["reviews"] = f"API refused ({e}); loader uses data/furry_paw_reviews_sample.json"
        out["reviews_api"] = "refused"
    say(f"reviews: {out['reviews']}")
    return out


if __name__ == "__main__":
    try:
        seed()
    except YextError as e:
        print(f"seed failed: {e}")
        sys.exit(1)
