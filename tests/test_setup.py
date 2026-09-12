"""
Tests for the configuration and onboarding endpoints.

These cover the precedence rules, the secret-handling contract, and the
first-run access rule - all places where a mistake is either a security
problem or a silently broken setup screen.
"""
import os

import pytest

from app.runtime_config import (
    LLMSettings,
    RuntimeConfig,
    config_path,
    load_config,
    mask_secret,
    reset_config,
    save_config,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point the config store at a temp file so tests never touch a real one."""
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "config.json"))
    reset_config()
    yield
    reset_config()


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def test_config_round_trips(clean_env):
    save_config(
        RuntimeConfig(
            onboarding_completed=True,
            llm=LLMSettings(provider="ollama", model="llama3.1"),
        )
    )
    loaded = load_config(refresh=True)
    assert loaded.onboarding_completed is True
    assert loaded.llm.provider == "ollama"
    assert loaded.llm.model == "llama3.1"


def test_unknown_keys_in_stored_config_are_ignored(clean_env):
    """An older or newer file must not make the application unbootable."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"llm": {"provider": "openai", "retired_option": 1}}', encoding="utf-8")

    loaded = load_config(refresh=True)
    assert loaded.llm.provider == "openai"


def test_corrupt_config_falls_back_to_defaults(clean_env):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    loaded = load_config(refresh=True)
    assert loaded.onboarding_completed is False


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("short", "•••••"),
        ("sk-abcdefghijklmnop", "sk-a…mnop"),
    ],
)
def test_mask_secret_never_reveals_the_middle(value, expected):
    assert mask_secret(value) == expected


# --------------------------------------------------------------------------
# Precedence
# --------------------------------------------------------------------------


def test_environment_wins_over_stored_configuration(monkeypatch, clean_env):
    save_config(RuntimeConfig(llm=LLMSettings(provider="ollama", model="llama3.1")))
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-from-env")

    from app.services.llm import build_llm_config

    config = build_llm_config()
    assert config.provider == "openai"
    assert config.api_key == "sk-from-env"


def test_stored_configuration_is_used_when_environment_is_unset(clean_env):
    save_config(
        RuntimeConfig(llm=LLMSettings(provider="gemini", model="gemini-2.5-flash", api_key="stored"))
    )

    from app.services.llm import build_llm_config

    config = build_llm_config()
    assert config.provider == "gemini"
    assert config.api_key == "stored"


def test_provider_defaults_fill_the_gaps(clean_env):
    save_config(RuntimeConfig(llm=LLMSettings(provider="ollama")))

    from app.services.llm import build_llm_config

    config = build_llm_config()
    assert config.model == "llama3.1"
    assert config.base_url == "http://localhost:11434"


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reports_setup_needed_on_a_fresh_install(client, clean_env):
    response = await client.get("/api/setup/status")
    assert response.status_code == 200
    assert response.json()["needs_setup"] is True


@pytest.mark.asyncio
async def test_providers_endpoint_describes_llms_and_databases(client, clean_env):
    response = await client.get("/api/setup/providers")
    assert response.status_code == 200

    body = response.json()
    assert {p["name"] for p in body["llm"]} >= {"openai", "anthropic", "gemini", "ollama"}
    names = {d["name"] for d in body["databases"]}
    assert {"sqlite", "postgresql", "supabase", "neon"} <= names


@pytest.mark.asyncio
async def test_completing_setup_persists_choices(client, clean_env):
    response = await client.post(
        "/api/setup/complete",
        json={"llm": {"provider": "ollama", "model": "llama3.1"}},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["onboarding_completed"] is True
    assert body["llm"]["provider"] == "ollama"
    assert load_config(refresh=True).llm.model == "llama3.1"


@pytest.mark.asyncio
async def test_setup_never_returns_a_secret_in_full(client, clean_env):
    # Asserted on the /complete response because it returns the same status
    # payload, and reading /status afterwards is correctly session-gated.
    response = await client.post(
        "/api/setup/complete",
        json={"llm": {"provider": "openai", "model": "gpt-4.1-mini", "api_key": "sk-supersecret-value"}},
    )

    assert "sk-supersecret-value" not in response.text
    assert response.json()["llm"]["api_key"] == "sk-s…alue"


@pytest.mark.asyncio
async def test_resaving_without_a_key_keeps_the_stored_one(client, clean_env):
    """The settings form never receives the real key, so it cannot send it back."""
    await client.post(
        "/api/setup/complete",
        json={"llm": {"provider": "openai", "model": "gpt-4.1-mini", "api_key": "sk-original"}},
    )
    await client.post(
        "/api/setup/complete",
        json={"llm": {"provider": "openai", "model": "gpt-4.1"}},
    )

    assert load_config(refresh=True).llm.api_key == "sk-original"


@pytest.mark.asyncio
async def test_unknown_provider_is_rejected(client, clean_env):
    response = await client.post(
        "/api/setup/complete", json={"llm": {"provider": "definitely-not-real"}}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_test_llm_reports_failure_without_raising(client, clean_env, httpx_mock):
    import httpx as _httpx

    httpx_mock.add_exception(_httpx.ConnectError("refused"))
    response = await client.post(
        "/api/setup/test-llm", json={"provider": "ollama", "model": "llama3.1"}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False


@pytest.mark.asyncio
async def test_test_llm_reports_missing_key_as_a_config_problem(client, clean_env):
    response = await client.post(
        "/api/setup/test-llm", json={"provider": "openai", "model": "gpt-4.1-mini"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "API key" in body["detail"]


# --------------------------------------------------------------------------
# First-run access rule
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_is_locked_down_once_configured(client, clean_env):
    """Open during first run, session-gated afterwards."""
    assert (await client.get("/api/setup/status")).status_code == 200

    await client.post("/api/setup/complete", json={"llm": {"provider": "ollama"}})

    locked = await client.get("/api/setup/status")
    assert locked.status_code == 401


# ---------------------------------------------------------------------------
# Live database switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switching_database_takes_effect_without_restart(client, clean_env, tmp_path, monkeypatch):
    """Saving a new database from Settings moves the running app onto it."""
    from sqlalchemy import select

    from app.database import connection
    from app.models.database import Organization

    # conftest pins DATABASE_URL in the environment so the suite is hermetic;
    # here the point is precisely that no environment override exists.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    original = connection.current_url()
    target = tmp_path / "switched.db"

    try:
        response = await client.post(
            "/api/setup/complete",
            json={"database": {"provider": "sqlite", "values": {"path": target.as_posix()}}},
        )
        assert response.status_code == 200, response.text
        assert target.exists()
        assert connection.current_url().endswith("switched.db")

        # Bootstrapped: schema created and the default workspace seeded.
        async with connection.AsyncSessionLocal() as session:
            orgs = (await session.execute(select(Organization))).scalars().all()
        assert len(orgs) == 1
    finally:
        await connection.switch_database(original)


@pytest.mark.asyncio
async def test_unreachable_database_is_refused_and_nothing_changes(client, clean_env, monkeypatch):
    from app.database import connection

    monkeypatch.delenv("DATABASE_URL", raising=False)
    before = connection.current_url()
    response = await client.post(
        "/api/setup/complete",
        json={"database": {"provider": "neon", "values": {"url": "postgresql://u:p@127.0.0.1:1/nope"}}},
    )
    assert response.status_code == 400
    assert "Could not switch" in response.json()["detail"]
    assert connection.current_url() == before
