"""The same page, driven by two providers.

    python3 examples/two_providers.py                       # no keys: rehearsal mode, Claude's wire format vs Gemini's, side by side
    python3 examples/two_providers.py anthropic openai      # any two of: anthropic gemini gemini-live openai openai-realtime local
    python3 examples/two_providers.py anthropic gemini --live   # the real models (needs ANTHROPIC_API_KEY and GEMINI_API_KEY in the environment)
    python3 examples/two_providers.py anthropic gemini-live --serve
        # two demo servers, http://127.0.0.1:8151 (first brain) and :8152 (second brain): open both in Chrome and ask the same question.
        # With gemini-live or openai-realtime the second tab opens a full-duplex live session (needs its key; Chrome asks for the microphone).

Without --live and --serve the question goes through the real /pilot/chat route of the demo app in-process, with PILOT_REHEARSAL=1: each brain's
own request builder and stream parser run against a fake of its API (server/providers/fakes.py), so the tour the page gets (actions and cues)
is the same, which is the point: the page does not care which model drives it. Nothing here reads a key file; keys come from the environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUESTION = "Show me the best match and why"
# What the browser would send: the live page's targets plus the pages it crawled (client/pilot.js builds this itself).
MANIFEST = {"app": {"name": "Matchboard (sample)", "description": ""}, "page": {"path": "/", "title": "Overview"},
            "targets": [{"id": "hero"}, {"id": "top-teaser"}, {"id": "ask-chips"}],
            "pages": [{"path": "/", "title": "Overview"}, {"path": "/matches", "title": "Matches", "targets": [{"id": "match-1"}, {"id": "filter-sector"}]},
                      {"path": "/startups/:slug", "title": "Startup", "targets": [{"id": "score"}, {"id": "why"}, {"id": "next-step"}, {"id": "funder"}]}]}


def run(brain: str, live: bool) -> dict:
    from fastapi.testclient import TestClient

    os.environ["PILOT_BRAIN"] = brain
    os.environ["PILOT_REHEARSAL"] = "0" if live else "1"
    from server.app import app, pilot
    pilot.pilot.limiter.reset()
    c = TestClient(app)
    status = c.get("/pilot/status").json()
    r = c.post("/pilot/chat", json={"messages": [{"role": "user", "content": QUESTION}], "manifest": MANIFEST})
    events = []
    for block in r.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((lines.get("event"), json.loads(lines.get("data") or "{}")))
    done = next((d for k, d in events if k == "done"), None)
    err = next((d for k, d in events if k == "error"), None)
    return {"brain": brain, "mode": status["mode"], "model": (done or {}).get("model"),
            "actions": [(a["id"], a["type"], a.get("target") or a.get("path")) for k, a in events if k == "action"],
            "said": (done or {}).get("text") or (err or {}).get("message", "")}


def serve(a: str, b: str) -> None:
    procs = []
    for port, brain in ((8151, a), (8152, b)):
        env = {**os.environ, "PILOT_BRAIN": brain}
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env))
        print(f"  {brain:16s} http://127.0.0.1:{port}")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


def main(argv: list[str]) -> None:
    names = [x for x in argv if not x.startswith("--")] or ["anthropic", "gemini"]
    if len(names) != 2:
        sys.exit("give two brains, e.g. anthropic gemini")
    if "--serve" in argv:
        serve(*names)
        return
    for r in (run(n, "--live" in argv) for n in names):
        print(f"\n== PILOT_BRAIN={r['brain']}  ({r['mode']}, model {r['model']})")
        for a in r["actions"]:
            print(f"   action {a[0]}: {a[1]} {a[2]}")
        print(f"   says: {r['said']}")


if __name__ == "__main__":
    main(sys.argv[1:])
