"""Voice routes: /api/voice/stt, /api/voice/tts, /api/voice/ask. The browser never sees a key."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import brain, stt, tts

log = logging.getLogger("kaiku.voice")
router = APIRouter()


@router.post("/api/voice/stt")
async def api_stt(request: Request):
    audio = await request.body()
    t0 = time.perf_counter()
    try:
        r = await stt.transcribe(audio, request.headers.get("content-type", "audio/webm").split(";")[0])
    except stt.SttError as e:
        raise HTTPException(e.status, e.msg)
    r["ms"] = round((time.perf_counter() - t0) * 1000)
    return r


@router.post("/api/voice/tts")
async def api_tts(body: dict):
    t0 = time.perf_counter()
    try:
        audio, cached = await tts.synthesize(str(body.get("text", "")))
    except tts.TtsError as e:
        raise HTTPException(e.status, e.msg)
    return Response(audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "private, max-age=3600", "X-Tts-Cache": "hit" if cached else "miss",
                             "X-Tts-Ms": str(round((time.perf_counter() - t0) * 1000))})


@router.post("/api/voice/ask")
async def api_ask(body: dict):
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "empty text")
    t0 = time.perf_counter()
    try:
        r = await brain.ask(text, page=str(body.get("page", "/")), lang=str(body.get("lang", "auto")), history=body.get("history"))
    except Exception as e:  # noqa: BLE001
        log.warning("ask failed: %s", type(e).__name__)
        return JSONResponse({"text": "Pahoittelut, en saanut yhteyttä aivoihini. Sorry, I could not reach my brain.", "actions": [], "error": True}, status_code=200)
    r["ms"] = round((time.perf_counter() - t0) * 1000)
    return r
