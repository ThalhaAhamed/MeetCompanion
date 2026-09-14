"""
Resolves the currently configured LLM provider for the application.

This is the single place that knows how environment settings map onto an
LLMConfig. Everything else asks for a provider and gets one, so swapping
vendors never touches application code.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.runtime_config import load_config, resolve
from app.providers.llm import (
    DESCRIPTORS,
    LLMConfig,
    LLMConfigError,
    LLMProvider,
    create_llm_provider,
)

# Settings names kept from before provider-agnostic configuration existed, so
# an existing .env keeps working without edits.
_LEGACY_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_LEGACY_MODELS = {
    "openai": "OPENAI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "groq": "GROQ_MODEL",
    "xai": "XAI_MODEL",
    "gemini": "GEMINI_MODEL",
}


def build_llm_config() -> LLMConfig:
    """
    Assemble an LLMConfig from the effective configuration.

    Precedence is environment variable, then the value saved during
    onboarding, then the provider's documented default. Legacy per-provider
    variable names are still honoured at the bottom of the chain.
    """
    stored = load_config().llm

    provider = str(resolve("LLM_PROVIDER", stored.provider, settings.LLM_PROVIDER) or "")
    provider = provider.strip().lower()
    if not provider:
        raise LLMConfigError("No LLM provider configured.")

    descriptor = DESCRIPTORS.get(provider)
    if descriptor is None:
        supported = ", ".join(sorted(DESCRIPTORS))
        raise LLMConfigError(
            f"Unknown LLM provider '{provider}'. Supported providers: {supported}."
        )

    api_key = resolve(
        "LLM_API_KEY",
        stored.api_key,
        settings.LLM_API_KEY or _legacy(_LEGACY_API_KEYS.get(provider)),
    )
    model = resolve(
        "LLM_MODEL",
        stored.model,
        settings.LLM_MODEL
        or _legacy(_LEGACY_MODELS.get(provider))
        or _default_field(descriptor, "model"),
    )
    base_url = resolve(
        "LLM_BASE_URL",
        stored.base_url,
        settings.LLM_BASE_URL or _default_field(descriptor, "base_url"),
    )

    temperature = stored.temperature
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE

    return LLMConfig(
        provider=provider,
        model=str(model or ""),
        api_key=api_key,
        base_url=base_url,
        temperature=float(temperature),
        max_tokens=stored.max_tokens or settings.LLM_MAX_TOKENS,
    )


def get_llm_provider() -> LLMProvider:
    """The configured provider, ready to use. Raises LLMConfigError if unusable."""
    return create_llm_provider(build_llm_config())


def try_get_llm_provider() -> Optional[LLMProvider]:
    """
    The configured provider, or None when configuration is absent or invalid.

    Used by callers that have a non-LLM fallback path and should degrade
    rather than fail outright.
    """
    try:
        return get_llm_provider()
    except LLMConfigError:
        return None


def _legacy(setting_name: Optional[str]) -> Optional[str]:
    if not setting_name:
        return None
    return getattr(settings, setting_name, None)


def _default_field(descriptor, key: str) -> Optional[str]:
    for field_spec in descriptor.fields:
        if field_spec.key == key and field_spec.default:
            return str(field_spec.default)
    return None
