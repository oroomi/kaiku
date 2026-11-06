"""Brains (the reasoning + tool-calling turn) and live voices, picked by PILOT_BRAIN and PILOT_VOICE (server/config.py).

  PILOT_BRAIN      the /pilot/chat turn uses          the live session (PILOT_VOICE) uses
  anthropic        Claude, Messages API (default)     -
  gemini           Gemini generateContent             gemini-live, when PILOT_VOICE=gemini-live
  gemini-live      Gemini generateContent (typed)     Gemini Live (the default voice for this brain)
  openai           OpenAI Responses                   openai-realtime, when PILOT_VOICE=openai-realtime
  openai-realtime  OpenAI Responses (typed)           OpenAI Realtime over WebRTC (the default voice for this brain)
  local            OpenAI-compatible Chat Completions (NVIDIA NIM / Nemotron, vLLM, llama.cpp, Ollama)
"""
from __future__ import annotations

from .anthropic import AnthropicBrain
from .gemini import GeminiBrain
from .openai import ChatBrain, OpenAIBrain

CHAT_BRAINS = {"anthropic": AnthropicBrain, "gemini": GeminiBrain, "gemini-live": GeminiBrain, "openai": OpenAIBrain,
               "openai-realtime": OpenAIBrain, "local": ChatBrain}


def chat_brain(brain: str):
    """A fresh brain for one /pilot/chat turn (brains keep the turn's own history, so one per turn)."""
    return CHAT_BRAINS.get(brain, AnthropicBrain)()


__all__ = ["AnthropicBrain", "GeminiBrain", "OpenAIBrain", "ChatBrain", "CHAT_BRAINS", "chat_brain"]
