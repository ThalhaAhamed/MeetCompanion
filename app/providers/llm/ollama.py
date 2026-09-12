"""
Adapter for a local Ollama server.

This is the provider that makes Meet Companion runnable with no API keys and
no data leaving the machine, so it is treated as a first-class option rather
than an afterthought.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from app.providers.llm.base import (
    ChatMessage,
    LLMError,
    LLMProvider,
    ProviderStatus,
)


class OllamaProvider(LLMProvider):
    name = "ollama"
    label = "Ollama (local)"
    supports_json_mode = True
    requires_api_key = False
    default_base_url = "http://localhost:11434"

    async def _complete(
        self,
        messages: List[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        options = {"temperature": self._temperature(temperature)}
        resolved_max_tokens = self._max_tokens(max_tokens)
        if resolved_max_tokens:
            options["num_predict"] = resolved_max_tokens

        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            _raise_for_status(response, self.label)
            data = response.json()

        content = (data.get("message") or {}).get("content")
        if not content:
            raise LLMError(f"{self.label} returned no message content.")
        return content

    async def health_check(self) -> ProviderStatus:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                _raise_for_status(response, self.label)
                data = response.json()
        except LLMError as exc:
            return ProviderStatus(ok=False, detail=str(exc))
        except httpx.HTTPError:
            return ProviderStatus(
                ok=False,
                detail=f"No Ollama server reachable at {self.base_url}. Is `ollama serve` running?",
            )

        models = sorted(
            str(item.get("name"))
            for item in data.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )
        if self.config.model and self.config.model not in models:
            return ProviderStatus(
                ok=False,
                detail=f"Model '{self.config.model}' is not pulled. Run: ollama pull {self.config.model}",
                models=models,
            )
        return ProviderStatus(ok=True, detail="Connected.", models=models)


def _raise_for_status(response: httpx.Response, label: str) -> None:
    if response.is_success:
        return
    detail = response.text.strip()
    if len(detail) > 500:
        detail = f"{detail[:500]}…"
    raise LLMError(f"{label} request failed ({response.status_code}): {detail}")
