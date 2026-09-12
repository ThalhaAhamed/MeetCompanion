"""
LLM provider interface.

Every provider speaks the same small contract: take chat messages, return text.
Providers are constructed from an explicit LLMConfig rather than reading global
settings, so the running configuration can be swapped at runtime (from the
Settings UI) and exercised in tests without patching module state.
"""
from __future__ import annotations

import json
import re
import httpx
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Literal, Optional

Role = Literal["system", "user", "assistant"]

DEFAULT_TIMEOUT_SECONDS = 120.0


class LLMError(RuntimeError):
    """Raised when a provider cannot fulfil a completion request."""


class LLMConfigError(LLMError):
    """Raised when a provider is configured incorrectly (missing key, bad URL)."""


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(slots=True)
class LLMConfig:
    """Everything needed to talk to one provider."""

    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderStatus:
    ok: bool
    detail: str
    models: List[str] = field(default_factory=list)


class LLMProvider(ABC):
    """Base class for all LLM adapters."""

    name: ClassVar[str]
    #: Human-readable label shown in onboarding and settings.
    label: ClassVar[str]
    #: Whether the provider can guarantee JSON-only output natively. When it
    #: cannot, complete_json() falls back to extracting JSON from prose.
    supports_json_mode: ClassVar[bool] = False
    #: Whether an API key is required to use the provider at all.
    requires_api_key: ClassVar[bool] = True
    #: Default endpoint used when the user does not override base_url.
    default_base_url: ClassVar[Optional[str]] = None

    def __init__(self, config: LLMConfig):
        self.config = config
        self.validate()

    def validate(self) -> None:
        if self.requires_api_key and not self.config.api_key:
            raise LLMConfigError(f"{self.label} requires an API key.")
        if not self.config.model:
            raise LLMConfigError(f"{self.label} requires a model name.")

    @property
    def base_url(self) -> str:
        url = self.config.base_url or self.default_base_url
        if not url:
            raise LLMConfigError(f"{self.label} requires a base URL.")
        return url.rstrip("/")

    async def complete(
        self,
        messages: List[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Return the assistant's reply as plain text.

        Transport failures - host down, DNS, timeout - surface as LLMError
        like any other provider failure, so callers with a fallback (memory
        extraction's rule-based parser, for one) take it instead of crashing.
        """
        try:
            return await self._complete(
                messages, json_mode=json_mode, temperature=temperature, max_tokens=max_tokens
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {self.label} at {self.base_url}: {exc}") from exc

    @abstractmethod
    async def _complete(
        self,
        messages: List[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Provider-specific request; may raise httpx errors."""

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """Verify the provider is reachable and correctly configured."""

    async def complete_json(
        self,
        messages: List[ChatMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Return the assistant's reply parsed as a JSON object.

        Providers without native JSON mode routinely wrap their output in prose
        or markdown fences, so the raw text is salvaged before giving up.
        """
        raw = await self.complete(
            messages,
            json_mode=self.supports_json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = extract_json_object(raw)
        if parsed is None:
            raise LLMError(f"{self.label} did not return parseable JSON.")
        return parsed

    def _temperature(self, override: Optional[float]) -> float:
        return self.config.temperature if override is None else override

    def _max_tokens(self, override: Optional[int]) -> Optional[int]:
        return self.config.max_tokens if override is None else override


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort recovery of a JSON object from model output.

    Tries the whole string, then a fenced code block, then the outermost
    balanced pair of braces.
    """
    if not raw:
        return None

    candidates = [raw.strip()]

    fenced = _JSON_FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
