"""LLM transport: an OpenAI-compatible chat client plus Ollama model listing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 1200
    timeout_sec: int = 120


class LLMClient(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str: ...


class OpenAICompatibleClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(self, messages: list[dict[str, str]]) -> str:
        config = self.config
        if not config.model.strip():
            raise LLMError("LLM model is not configured")

        base_url = config.base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if config.api_key.strip():
            headers["Authorization"] = f"Bearer {config.api_key.strip()}"

        payload = {
            "model": config.model.strip(),
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": False,
        }
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=config.timeout_sec,
            )
        except requests.RequestException as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if not resp.ok:
            raise LLMError(f"LLM request failed: {resp.status_code} {resp.text[:1000]}")

        try:
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response: {resp.text[:1000]}") from exc


def list_ollama_models(base_api_url: str = "http://127.0.0.1:11434/api") -> list[str]:
    try:
        resp = requests.get(f"{base_api_url.rstrip('/')}/tags", timeout=2)
        if not resp.ok:
            return []
        models = resp.json().get("models", [])
        return [str(model.get("name")) for model in models if model.get("name")]
    except requests.RequestException:
        return []
