"""Minimal chat client for OpenAI-compatible and Anthropic APIs.

Configured entirely from the environment so the same code talks to OpenAI,
Anthropic, Groq, OpenRouter or a local Ollama server.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatLLM:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        self.name = model
        self._model, self._url = model, base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def complete(self, system: str, user: str) -> str:
        body = {
            "model": self._model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        r = httpx.post(self._url, json=body, headers=self._headers, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""


class AnthropicLLM:
    def __init__(self, api_key: str, model: str):
        self.name = model
        self._model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}

    def complete(self, system: str, user: str) -> str:
        body = {
            "model": self._model,
            "max_tokens": 600,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        r = httpx.post("https://api.anthropic.com/v1/messages", json=body, headers=self._headers, timeout=60)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


def from_env() -> LLM | None:
    """Return a client if credentials are configured, else None (offline mode)."""
    model = os.getenv("LLM_MODEL")
    if os.getenv("ANTHROPIC_API_KEY") and model:
        return AnthropicLLM(os.environ["ANTHROPIC_API_KEY"], model)
    if os.getenv("OPENAI_API_KEY") and model:
        return OpenAICompatLLM(
            os.environ["OPENAI_API_KEY"], model, os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
    return None
