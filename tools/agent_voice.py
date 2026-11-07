#!/usr/bin/env python3
"""Set the live Kaiku call agent's voice to ELEVENLABS_VOICE_ID from /root/hack/kaiku/.env (update-agent only pushes the
language fields; the voice lives in conversation_config.tts.voice_id). Prints ids only, never a key.
Usage: /root/hack/kaiku/.venv/bin/python /root/hack/kaiku/tools/agent_voice.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/root/hack/kaiku")
from kaiku.contact import whatsapp as W  # noqa: E402


def main() -> int:
    W.load_env()
    key = os.environ.get("ELEVENLABS_API_KEY", ""); aid = os.environ.get("ELEVENLABS_AGENT_ID", "")
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip().strip('"')
    if not (key and aid and voice):
        print("missing ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID or ELEVENLABS_VOICE_ID in .env"); return 2
    H = {"xi-api-key": key, "Content-Type": "application/json"}
    body = {"conversation_config": {"tts": {"voice_id": voice, "stability": 0.5, "similarity_boost": 0.75, "style": 0.2, "use_speaker_boost": True, "speed": 0.85, "model_id": "eleven_turbo_v2"}}}   # calmer delivery (Dayo 7 Nov: the default pace sounded hurried)
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/convai/agents/{aid}", data=json.dumps(body).encode(), method="PATCH", headers=H)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read()); st = r.status
    except urllib.error.HTTPError as e:
        print("PATCH failed:", e.code, (e.read() or b"")[:300].decode(errors="replace")); return 1
    now = (d.get("conversation_config") or {}).get("tts", {}).get("voice_id")
    tts = (d.get("conversation_config") or {}).get("tts", {})
    print(f"PATCH {st} | agent voice now: {now} | wanted: {voice} | speed {tts.get('speed')} stability {tts.get('stability')} | {'ok' if now == voice else 'NOT switched'}")
    return 0 if now == voice else 1


if __name__ == "__main__":
    sys.exit(main())
