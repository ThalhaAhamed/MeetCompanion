"""
Persisted user configuration.

Settings chosen during onboarding or in the Settings screen are written to a
JSON file next to the database, so a self-hosted install is configured through
the UI rather than by hand-editing environment variables.

Precedence is deliberate: an explicitly set environment variable always wins,
so container and CI deployments stay declarative and reproducible. The UI
reports those fields as environment-managed instead of silently failing to
save them.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

CONFIG_PATH_ENV = "MEET_COMPANION_CONFIG"
DEFAULT_CONFIG_PATH = Path("data/config.json")

#: Fields whose values must never be returned to a client in full.
SECRET_FIELDS = {"api_key", "url", "webhook_secret"}


@dataclass
class LLMSettings:
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class DatabaseSettings:
    url: Optional[str] = None


@dataclass
class MeetStreamSettings:
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class AgentTemplateSettings:
    """
    The starting point every new MeetStream agent is created from.

    Fields left as None fall back to the built-in defaults in app.api.agent,
    so a fresh install has a working template before anyone edits it. Text
    fields may contain ``{agent_name}``, which is filled in at creation time.
    """
    system_prompt: Optional[str] = None
    first_message: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    voice: Optional[str] = None
    temperature: Optional[float] = None
    mode: Optional[str] = None
    response_modality: Optional[str] = None
    tool_results_to_chat: Optional[bool] = None


@dataclass
class RuntimeConfig:
    onboarding_completed: bool = False
    llm: LLMSettings = field(default_factory=LLMSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    meetstream: MeetStreamSettings = field(default_factory=MeetStreamSettings)
    agent_template: AgentTemplateSettings = field(default_factory=AgentTemplateSettings)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RuntimeConfig":
        return cls(
            onboarding_completed=bool(raw.get("onboarding_completed", False)),
            llm=LLMSettings(**_section(raw, "llm", LLMSettings)),
            database=DatabaseSettings(**_section(raw, "database", DatabaseSettings)),
            meetstream=MeetStreamSettings(**_section(raw, "meetstream", MeetStreamSettings)),
            agent_template=AgentTemplateSettings(**_section(raw, "agent_template", AgentTemplateSettings)),
        )


def _section(raw: Dict[str, Any], key: str, cls: type) -> Dict[str, Any]:
    """Read one section, ignoring unknown keys so older files stay loadable."""
    known = {f for f in cls.__dataclass_fields__}
    return {k: v for k, v in (raw.get(key) or {}).items() if k in known}


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_PATH_ENV) or DEFAULT_CONFIG_PATH)


_cache: Optional[RuntimeConfig] = None


def load_config(*, refresh: bool = False) -> RuntimeConfig:
    global _cache
    if _cache is not None and not refresh:
        return _cache

    path = config_path()
    if not path.exists():
        _cache = RuntimeConfig()
        return _cache

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _cache = RuntimeConfig.from_dict(raw)
    except (OSError, ValueError) as exc:
        # A corrupt config must not make the application unbootable; defaults
        # put the user back into onboarding instead.
        print(f"[WARN] Could not read {path} ({exc}). Falling back to defaults.")
        _cache = RuntimeConfig()
    return _cache


def save_config(config: RuntimeConfig) -> RuntimeConfig:
    """Persist configuration atomically so a crash cannot truncate the file."""
    global _cache
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(config.to_dict(), handle, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)

    try:
        # Best effort: the file holds API keys, so restrict it where the
        # platform supports doing so.
        path.chmod(0o600)
    except OSError:
        pass

    _cache = config
    return config


def update_config(**sections: Any) -> RuntimeConfig:
    """Replace whole sections of the stored configuration."""
    current = load_config()
    return save_config(replace(current, **sections))


def reset_config() -> RuntimeConfig:
    """Forget stored configuration and return to first-run onboarding."""
    global _cache
    path = config_path()
    path.unlink(missing_ok=True)
    _cache = RuntimeConfig()
    return _cache


# ---------------------------------------------------------------------------
# Environment precedence
# ---------------------------------------------------------------------------


def env_override(name: str) -> Optional[str]:
    """The environment value for `name`, if it was explicitly set."""
    value = os.environ.get(name)
    return value if value not in (None, "") else None


def is_env_managed(name: str) -> bool:
    """
    True when the value came from the process environment or the .env file.

    pydantic-settings reads .env into `settings` without touching os.environ,
    so the fields it populated are checked too - a URL someone wrote in .env
    is just as deliberate as one exported in a shell.
    """
    if env_override(name) is not None:
        return True
    return name in settings.model_fields_set


def resolve(env_name: str, stored: Any, fallback: Any = None) -> Any:
    """Apply precedence: explicit environment variable, then stored, then default."""
    override = env_override(env_name)
    if override is not None:
        return override
    if stored not in (None, ""):
        return stored
    return fallback


def mask_secret(value: Optional[str]) -> Optional[str]:
    """Render a secret safely for display: never the full value."""
    if not value:
        return None
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def describe_environment_managed() -> Dict[str, bool]:
    """Which settings the UI must render as read-only because the environment set them."""
    return {
        "llm.provider": is_env_managed("LLM_PROVIDER"),
        "llm.model": is_env_managed("LLM_MODEL"),
        "llm.api_key": is_env_managed("LLM_API_KEY"),
        "llm.base_url": is_env_managed("LLM_BASE_URL"),
        "database.url": is_env_managed("DATABASE_URL"),
        "meetstream.api_key": is_env_managed("MEETSTREAM_API_KEY"),
    }


def is_configured() -> bool:
    """
    Whether the application has enough configuration to skip onboarding.

    An environment-driven deployment is considered configured even if the
    onboarding flow was never run, so containers start ready to use.
    """
    config = load_config()
    if config.onboarding_completed:
        return True
    return is_env_managed("LLM_PROVIDER") and (
        is_env_managed("LLM_API_KEY")
        or (os.environ.get("LLM_PROVIDER") or settings.LLM_PROVIDER) == "ollama"
    )
