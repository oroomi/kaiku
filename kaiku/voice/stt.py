"""Speech to text: ElevenLabs scribe_v1 through our server (the browser never sees the key)."""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("kaiku.voice.stt")
URL = "https://api.elevenlabs.io/v1/speech-to-text"
MAX_BYTES = 6_000_000
MIN_BYTES = 800  # a real clip is never smaller; empty/accidental taps are refused before any API call


class SttError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


async def transcribe(audio: bytes, content_type: str = "audio/webm", client: httpx.AsyncClient | None = None) -> dict:
    if not audio or len(audio) < MIN_BYTES:
        raise SttError(400, "empty or too short audio")
    if len(audio) > MAX_BYTES:
        raise SttError(413, "audio too large")
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        raise SttError(503, "speech to text is not configured")
    ext = "mp4" if "mp4" in content_type or "aac" in content_type else "ogg" if "ogg" in content_type else "webm"
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
    try:
        r = await client.post(URL, headers={"xi-api-key": key}, data={"model_id": "scribe_v1", "tag_audio_events": "false"},
                              files={"file": (f"clip.{ext}", audio, content_type or "audio/webm")})
    except httpx.HTTPError as e:
        log.warning("stt request failed: %s", type(e).__name__)
        raise SttError(502, "speech service unreachable")
    finally:
        if own:
            await client.aclose()
    if r.status_code != 200:
        log.warning("stt upstream status %s", r.status_code)
        raise SttError(502, "speech service refused the clip")
    j = r.json()
    return {"text": (j.get("text") or "").strip(), "language": j.get("language_code")}
