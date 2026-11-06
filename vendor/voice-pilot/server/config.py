"""Settings, read from the environment on every call (so tests can monkeypatch and a restart picks up a new EnvironmentFile).

Keys are only ever read from os.environ and are never returned, logged or echoed. Every name is listed in .env.example; the provider settings
(PILOT_BRAIN, PILOT_VOICE and the per-provider models) are in the README's provider matrix.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger("voice_pilot")


def _get(name: str, default, cast=str):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return cast(str(raw).strip())
    except (TypeError, ValueError):
        log.warning("%s=%r is not a valid %s; using %r", name, raw, cast.__name__, default)
        return default


@dataclass(frozen=True)
class Settings:
    assistant_name: str
    model: str
    effort: str
    thinking: str            # "adaptive" (default) or "between_tools" (Sonnet 5.5 only: no extended thinking, lowest latency)
    fallbacks: str           # "default" sends the server-side refusal fallback (Claude API); "off" sends nothing
    max_tokens: int
    max_steps: int
    timeout_s: float
    turn_deadline_s: float
    rate_per_min: int
    daily_turns: int
    trust_proxy: bool        # read the client IP from cf-connecting-ip / x-forwarded-for (only behind a proxy you control)
    tts_rate_per_min: int
    max_actions: int
    input_chars: int
    history_turns: int
    rehearsal: bool
    tts_voice_id: str
    tts_model: str
    tts_format: str
    tts_daily_chars: int
    tts_max_chars: int
    tts_cache_items: int
    # ---- providers (server/providers/); the defaults keep the Anthropic + ElevenLabs path exactly as it was ----
    brain: str = "anthropic"          # PILOT_BRAIN: anthropic | gemini | gemini-live | openai | openai-realtime | local
    voice: str = "elevenlabs"         # PILOT_VOICE, resolved: elevenlabs | browser | gemini-live | openai-realtime
    voice_explicit: bool = False      # PILOT_VOICE was set (status then names brain and voice)
    gemini_model: str = "gemini-3.8-flash"
    gemini_live_model: str = "gemini-3.8-live"
    gemini_thinking: str = "on"       # "off" sends no thinkingConfig
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    openai_model: str = "gpt-6.1-sol"
    openai_base_url: str = "https://api.openai.com/v1"
    realtime_model: str = "gpt-realtime-2.1"
    realtime_voice: str = "marin"
    realtime_transcribe: str = "gpt-live-transcribe"
    local_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    local_base_url: str = "http://127.0.0.1:8000/v1"
    live_voice_name: str = "Kore"     # Gemini Live prebuilt voice
    live_start_s: int = 120           # how long a minted live token may wait before the session starts
    live_tool_rate_per_min: int = 90
    live_max_calls: int = 300         # tool calls per live session
    live_daily_sessions: int = 100    # live sessions per UTC day (each one is minutes of audio, so it costs far more than a question)

    @property
    def live(self) -> str | None:
        """The live session the browser should open, or None for the classic path (Web Speech + /chat + /tts)."""
        return self.voice if self.voice in LIVE_VOICES else None


BRAINS = ("anthropic", "gemini", "gemini-live", "openai", "openai-realtime", "local")
VOICES = ("elevenlabs", "browser", "gemini-live", "openai-realtime")
LIVE_VOICES = ("gemini-live", "openai-realtime")
LIVE_FAMILY = {"gemini-live": ("gemini", "gemini-live"), "openai-realtime": ("openai", "openai-realtime")}


def _brain_voice() -> tuple[str, str, bool]:
    brain = _get("PILOT_BRAIN", "anthropic").lower()
    if brain not in BRAINS:
        log.warning("PILOT_BRAIN=%r is not one of %s; using anthropic", brain, ", ".join(BRAINS))
        brain = "anthropic"
    raw = _get("PILOT_VOICE", "").lower()
    voice = raw or (brain if brain in LIVE_VOICES else "elevenlabs")
    if voice not in VOICES:
        log.warning("PILOT_VOICE=%r is not one of %s; using elevenlabs", raw, ", ".join(VOICES))
        voice = "elevenlabs"
    if voice in LIVE_FAMILY and brain not in LIVE_FAMILY[voice]:
        log.warning("PILOT_VOICE=%s needs PILOT_BRAIN %s; using elevenlabs", voice, " or ".join(LIVE_FAMILY[voice]))
        voice = "elevenlabs"
    return brain, voice, bool(raw)


def settings() -> Settings:
    brain, voice, voice_explicit = _brain_voice()
    local_base = _get("PILOT_LOCAL_BASE_URL", "") or ("https://integrate.api.nvidia.com/v1" if os.environ.get("NVIDIA_API_KEY", "").strip()
                                                     else "http://127.0.0.1:8000/v1")
    return Settings(
        assistant_name=_get("PILOT_ASSISTANT_NAME", "Aava"),
        model=_get("PILOT_MODEL", "claude-sonnet-5-5"),
        effort=_get("PILOT_EFFORT", "low"),
        thinking=_get("PILOT_THINKING", "adaptive"),
        fallbacks=_get("PILOT_FALLBACKS", "default"),
        max_tokens=_get("PILOT_MAX_TOKENS", 4096, int),
        max_steps=_get("PILOT_MAX_STEPS", 5, int),
        timeout_s=_get("PILOT_TIMEOUT_S", 30.0, float),
        turn_deadline_s=_get("PILOT_TURN_DEADLINE_S", 45.0, float),
        rate_per_min=_get("PILOT_RATE_PER_MIN", 12, int),
        daily_turns=_get("PILOT_DAILY_TURNS", 400, int),
        trust_proxy=_get("PILOT_TRUST_PROXY", "0") in ("1", "true", "yes", "on"),
        tts_rate_per_min=_get("PILOT_TTS_RATE_PER_MIN", 40, int),
        max_actions=_get("PILOT_MAX_ACTIONS", 8, int),
        input_chars=_get("PILOT_INPUT_CHARS", 600, int),
        history_turns=_get("PILOT_HISTORY_TURNS", 10, int),
        rehearsal=_get("PILOT_REHEARSAL", "0") in ("1", "true", "yes", "on"),
        tts_voice_id=_get("ELEVENLABS_VOICE_ID", ""),
        tts_model=_get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        tts_format=_get("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
        tts_daily_chars=_get("PILOT_TTS_DAILY_CHARS", 20000, int),
        tts_max_chars=_get("PILOT_TTS_MAX_CHARS", 600, int),
        tts_cache_items=_get("PILOT_TTS_CACHE_ITEMS", 200, int),
        brain=brain,
        voice=voice,
        voice_explicit=voice_explicit,
        gemini_model=_get("PILOT_GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_live_model=_get("PILOT_GEMINI_LIVE_MODEL", "gemini-3.8-live"),
        gemini_thinking=_get("PILOT_GEMINI_THINKING", "on").lower(),
        gemini_base_url=_get("PILOT_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
        openai_model=_get("PILOT_OPENAI_MODEL", "gpt-6.1-sol"),
        openai_base_url=_get("PILOT_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        realtime_model=_get("PILOT_REALTIME_MODEL", "gpt-realtime-2.1"),
        realtime_voice=_get("PILOT_REALTIME_VOICE", "marin"),
        realtime_transcribe=_get("PILOT_REALTIME_TRANSCRIBE", "gpt-live-transcribe"),
        local_model=_get("PILOT_LOCAL_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        local_base_url=local_base,
        live_voice_name=_get("PILOT_GEMINI_VOICE", "Kore"),
        live_start_s=_get("PILOT_LIVE_START_S", 120, int),
        live_tool_rate_per_min=_get("PILOT_LIVE_TOOL_RATE_PER_MIN", 90, int),
        live_max_calls=_get("PILOT_LIVE_MAX_CALLS", 300, int),
        live_daily_sessions=_get("PILOT_LIVE_DAILY_SESSIONS", 100, int),
    )


def anthropic_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def elevenlabs_key() -> str:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()
