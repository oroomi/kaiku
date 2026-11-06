"""Text to speech: ElevenLabs eleven_flash_v2_5 through our server, cached by text hash in data/tts_cache/."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx

log = logging.getLogger("kaiku.voice.tts")
CACHE = Path(__file__).resolve().parents[2] / "data" / "tts_cache"
MODEL = "eleven_flash_v2_5"
FORMAT = "mp3_44100_64"
MAX_CHARS = 700
DAILY_CHARS = int(os.getenv("VOICE_TTS_DAILY_CHARS", "80000"))  # cost guard
_spent = {"day": "", "n": 0}


class TtsError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


def clean(text: str) -> str:
    return " ".join((text or "").replace("*", "").replace("#", "").replace("`", "").split())


def key_for(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}|{MODEL}|{FORMAT}|{text}".encode()).hexdigest()


async def synthesize(text: str, client: httpx.AsyncClient | None = None, cache_dir: Path | None = None) -> tuple[bytes, bool]:
    """Returns (mp3 bytes, from_cache)."""
    text = clean(text)
    if not text:
        raise TtsError(400, "empty text")
    if len(text) > MAX_CHARS:
        raise TtsError(413, "text too long")
    voice = os.getenv("ELEVENLABS_VOICE_ID", "")
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not voice or not key:
        raise TtsError(503, "text to speech is not configured")
    d = cache_dir or CACHE
    f = d / (key_for(text, voice) + ".mp3")
    if f.exists() and f.stat().st_size > 0:
        return f.read_bytes(), True
    day = time.strftime("%Y-%m-%d")
    if _spent["day"] != day:
        _spent.update(day=day, n=0)
    if _spent["n"] + len(text) > DAILY_CHARS:
        raise TtsError(429, "daily voice budget used")
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
    try:
        r = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{quote(voice, safe='')}?output_format={FORMAT}",
                              headers={"xi-api-key": key, "Accept": "audio/mpeg"},
                              json={"text": text, "model_id": MODEL, "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}})
    except httpx.HTTPError as e:
        log.warning("tts request failed: %s", type(e).__name__)
        raise TtsError(502, "voice service unreachable")
    finally:
        if own:
            await client.aclose()
    if r.status_code != 200 or not r.content:
        log.warning("tts upstream status %s", r.status_code)
        raise TtsError(502, "voice service refused")
    _spent["n"] += len(text)
    try:
        d.mkdir(parents=True, exist_ok=True)
        f.write_bytes(r.content)
    except OSError:
        pass
    return r.content, False
