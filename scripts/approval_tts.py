#!/usr/bin/env python3
"""Narration for the approval cut: one ElevenLabs TTS call per line (Kaiku's voice). Key and voice id are read from .env, never printed.
Usage: approval_tts.py  -> video/appr/vo/<id>.mp3 + video/appr/vo/durations.json"""
import os, json, subprocess, sys, time, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("/root/hack/kaiku/.env")
KEY = os.environ["ELEVENLABS_API_KEY"]; VOICE = os.environ["ELEVENLABS_VOICE_ID"]
OUT = Path("/root/hack/kaiku/video/appr/vo"); OUT.mkdir(parents=True, exist_ok=True)
LINES = json.load(open("/root/hack/kaiku/video/appr/lines.json"))
dur = {}
for lid, text in LINES.items():
    f = OUT / f"{lid}.mp3"
    if not f.exists() or "--force" in sys.argv:
        for attempt in range(2):
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128",
                              headers={"xi-api-key": KEY, "Content-Type": "application/json"},
                              json={"text": text, "model_id": os.environ.get("KAIKU_TTS_MODEL", "eleven_multilingual_v2"),
                                    "voice_settings": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.15}}, timeout=90)
            if r.status_code == 200 and len(r.content) > 2000: f.write_bytes(r.content); break
            print(lid, "TTS fail", r.status_code, r.text[:80].replace(KEY, "***")); time.sleep(2)
        else: sys.exit(f"TTS failed twice on {lid}")
    dur[lid] = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))
json.dump(dur, open(OUT / "durations.json", "w"), indent=1); print(json.dumps({k: round(v, 2) for k, v in dur.items()}))
