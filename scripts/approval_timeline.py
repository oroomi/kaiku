#!/usr/bin/env python3
"""Builds video/appr/timeline.json (beats, absolute starts, captions split by sentence, voice cues) from beats.json + lines.json + vo/durations.json,
and the live datasetIds (GET /api/feed) for the FIWARE beat."""
import json, re, requests
from pathlib import Path
R = Path("/root/hack/kaiku/video/appr")
B = json.load(open(R/"beats.json")); L = json.load(open(R/"lines.json")); D = json.load(open(R/"vo/durations.json"))
OP = B["opener"]; t = OP; beats = []; voice = [("o1", 0.05), ("o2", 2.25), ("o3", 4.15)]
for b in B["beats"]:
    caps = []
    for lid, off in b["lines"].items():
        voice.append((lid, t + off))
        sents = [x for q in re.findall(r"[^.?!]+[.?!]", L[lid]) for x in (re.findall(r"[^,]+,|[^,]+$", q) if len(q) > 72 else [q])]; tot = sum(len(s) for s in sents); a = off
        for s in sents:
            d = D[lid] * len(s) / tot; caps.append({"id": lid, "a": round(a, 2), "b": round(a + d + 0.2, 2), "text": s.strip()}); a += d
    beats.append({"id": b["id"], "start": round(t, 3), "dur": b["dur"], "caps": caps}); t += b["dur"]
ds = {}
for s in requests.get("https://kaiku.hankintaviikko.fi/api/feed/furry-paw?date=2026-12-17", timeout=30).json()["suggestions"]:
    for r in s["reasons"]: ds[r["source"]] = r["dataset_id"]
out = {"opener": OP, "total": round(t, 3), "beats": beats, "voice": [{"id": i, "at": round(a, 3), "dur": D[i]} for i, a in voice], "datasets": [{"source": k, "id": v} for k, v in ds.items()]}
json.dump(out, open(R/"timeline.json", "w"), indent=1); print("total", out["total"], "datasets", len(ds))
