"""
Security tests that go through HTTP, the way an attacker would.

Covers the trust boundaries described in SECURITY.md: workspace isolation,
owner-only configuration, the session cookie's signing key, rate limits,
generated MCP tokens and webhook signature enforcement.
"""
import time
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.database.connection import AsyncSessionLocal
from app.main import app
from app.middleware.auth_gate import COOKIE_NAME, SESSION_TTL_SECONDS, sign_session
from app.middleware.limits import rate_limiter
from app.models.database import Organization, User
from app.models.schemas import ActionItemUpdate


async def _signup(client, email, *, workspace=None, join_code=None):
    body = {"name": email.split("@")[0], "email": email, "password": "correct-horse-battery"}
    if workspace:
        body["workspace_name"] = workspace
    if join_code:
        body["join_code"] = join_code
    resp = await client.post("/api/members", json=body)
    assert resp.status_code == 200, resp.text
    login = await client.post("/api/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert login.status_code == 200, login.text
    # The cookie is marked Secure; the test transport is plain http, so the
    # jar would withhold it. Carry it explicitly.
    token = login.headers["set-cookie"].split(f"{COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    client.cookies.set(COOKIE_NAME, token)
    return resp.json()


def _client(cookies=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", cookies=cookies or {})


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


# ---------------------------------------------------------------------------
# Workspace isolation over HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_other_workspace_cannot_read_or_change_my_data():
    async with _client() as a, _client() as b:
        await _signup(a, f"a-{uuid.uuid4().hex[:6]}@example.com", workspace="Alpha")
        await _signup(b, f"b-{uuid.uuid4().hex[:6]}@example.com", workspace="Beta")

        note = (await a.post("/api/notebook/notes", json={"title": "Alpha secret", "content": "- [ ] ship it"})).json()
        folder = (await a.post("/api/notebook/folders", json={"name": "Alpha folder"})).json()
        meeting = (
            await a.post(
                "/api/meetings/upload",
                json={"title": "Alpha call", "transcript": "Sam: I will send the SOC2 report tomorrow."},
            )
        ).json()
        items = (await a.get("/api/action-items")).json()
        item_id = items["action_items"][0]["id"]

        assert (await b.get(f"/api/notebook/notes/{note['id']}")).status_code == 404
        assert (await b.patch(f"/api/notebook/notes/{note['id']}", json={"title": "pwned"})).status_code == 404
        assert (await b.delete(f"/api/notebook/notes/{note['id']}")).status_code == 404
        assert (await b.patch(f"/api/notebook/folders/{folder['id']}", json={"name": "pwned"})).status_code == 404
        assert (await b.get(f"/api/meetings/{meeting['id']}")).status_code == 404
        assert (await b.get(f"/api/meetings/{meeting['id']}/transcript")).status_code == 404
        assert (await b.delete(f"/api/meetings/{meeting['id']}")).status_code == 404
        assert (await b.patch(f"/api/action-items/{item_id}", json={"status": "completed"})).status_code == 404

        listing = (await b.get("/api/notebook/notes")).json()
        titles = [n["title"] for n in (listing["notes"] if isinstance(listing, dict) else listing)]
        assert "Alpha secret" not in titles
        assert (await b.post("/api/search/memory", json={"query": "SOC2"})).json()["total_results"] == 0

        # Still intact for its owner.
        assert (await a.get(f"/api/notebook/notes/{note['id']}")).json()["title"] == "Alpha secret"


@pytest.mark.asyncio
async def test_members_of_other_workspaces_are_invisible():
    async with _client() as a, _client() as b:
        await _signup(a, f"a-{uuid.uuid4().hex[:6]}@example.com", workspace="Alpha")
        b_user = await _signup(b, f"b-{uuid.uuid4().hex[:6]}@example.com", workspace="Beta")
        emails = [m["email"] for m in (await a.get("/api/members")).json()["members"]]
        assert b_user["email"] not in emails
        assert (await a.delete(f"/api/members/{b_user['id']}")).status_code == 404
        assert (await a.post(f"/api/members/{b_user['id']}/reset-password", json={"new_password": "hijacked-pw"})).status_code == 404


# ---------------------------------------------------------------------------
# Roles: owners vs members
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_creator_is_owner_and_joiner_is_member():
    async with _client() as a, _client() as b:
        owner = await _signup(a, f"o-{uuid.uuid4().hex[:6]}@example.com", workspace="Gamma")
        assert owner["role"] == "owner"
        code = (await a.get("/api/members/workspace")).json()["join_code"]
        member = await _signup(b, f"m-{uuid.uuid4().hex[:6]}@example.com", join_code=code)
        assert member["role"] == "member"
        assert (await b.get("/api/auth/check")).json()["member"]["role"] == "member"


@pytest.mark.asyncio
async def test_member_cannot_change_server_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from app import runtime_config

    runtime_config.load_config(refresh=True)
    runtime_config.update_config(onboarding_completed=True)

    async with _client() as a, _client() as b:
        await _signup(a, f"o-{uuid.uuid4().hex[:6]}@example.com", workspace="Delta")
        code = (await a.get("/api/members/workspace")).json()["join_code"]
        await _signup(b, f"m-{uuid.uuid4().hex[:6]}@example.com", join_code=code)

        for path, body in (
            ("/api/setup/complete", {"llm": {"provider": "ollama", "model": "llama3.1"}}),
            ("/api/setup/reset", None),
            ("/api/setup/test-database", {"url": "sqlite+aiosqlite:///data/x.db"}),
            ("/api/setup/test-llm", {"provider": "ollama", "model": "llama3.1"}),
        ):
            resp = await b.post(path, json=body)
            assert resp.status_code == 403, (path, resp.text)
        assert (await b.put("/api/agent/template", json={"first_message": "hi"})).status_code == 403

        status = (await b.get("/api/setup/status")).json()
        assert status["read_only"] is True
        assert "api_key" not in status["llm"]
        assert "url" not in status["database"]

        # The owner still can, and gets the full view.
        assert (await a.post("/api/setup/test-llm", json={"provider": "ollama", "model": "llama3.1"})).status_code == 200
        assert "read_only" not in (await a.get("/api/setup/status")).json()

    runtime_config.load_config(refresh=True)


@pytest.mark.asyncio
async def test_setup_requires_sign_in_once_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "config.json"))
    from app import runtime_config

    runtime_config.load_config(refresh=True)
    runtime_config.update_config(onboarding_completed=True)
    async with _client() as anon:
        assert (await anon.post("/api/setup/reset")).status_code == 401
        assert (await anon.post("/api/setup/complete", json={})).status_code == 401
    runtime_config.load_config(refresh=True)


@pytest.mark.asyncio
async def test_member_can_only_remove_self_and_last_owner_is_protected():
    async with _client() as a, _client() as b:
        owner = await _signup(a, f"o-{uuid.uuid4().hex[:6]}@example.com", workspace="Epsilon")
        code = (await a.get("/api/members/workspace")).json()["join_code"]
        member = await _signup(b, f"m-{uuid.uuid4().hex[:6]}@example.com", join_code=code)

        assert (await b.delete(f"/api/members/{owner['id']}")).status_code == 403
        assert (await b.post(f"/api/members/{owner['id']}/role", json={"role": "member"})).status_code == 403
        assert (await a.post(f"/api/members/{owner['id']}/role", json={"role": "member"})).status_code == 400

        promoted = await a.post(f"/api/members/{member['id']}/role", json={"role": "owner"})
        assert promoted.json()["role"] == "owner"
        assert (await a.post(f"/api/members/{owner['id']}/role", json={"role": "member"})).status_code == 200


# ---------------------------------------------------------------------------
# Sessions and secrets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cookie_signed_with_a_different_key_is_rejected():
    async with _client() as a:
        me = await _signup(a, f"s-{uuid.uuid4().hex[:6]}@example.com", workspace="Zeta")
    import hashlib
    import hmac

    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{expires}.{me['id']}"
    forged = payload + "." + hmac.new(b"meet_companion_secure_salt_2026", payload.encode(), hashlib.sha256).hexdigest()
    async with _client({COOKIE_NAME: forged}) as forger:
        assert (await forger.get("/api/notebook/notes")).status_code == 401
    genuine = sign_session(me["id"], expires)
    async with _client({COOKIE_NAME: genuine}) as real:
        assert (await real.get("/api/notebook/notes")).status_code == 200


def test_placeholder_secrets_are_never_accepted(monkeypatch, tmp_path):
    from app import secrets as app_secrets

    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("SESSION_SECRET", "change-me-to-a-random-string")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "dev-mcp-token-meetstream-2026")
    app_secrets.reset_for_tests()
    try:
        generated = app_secrets.session_secret()
        assert generated != "change-me-to-a-random-string"
        assert len(generated) >= 32
        assert (tmp_path / "session.key").read_text().strip() == generated
        assert app_secrets.configured_mcp_token() is None
    finally:
        app_secrets.reset_for_tests()


@pytest.mark.asyncio
async def test_new_workspaces_get_unique_random_mcp_tokens():
    async with _client() as a, _client() as b:
        await _signup(a, f"t-{uuid.uuid4().hex[:6]}@example.com", workspace="Theta")
        await _signup(b, f"t-{uuid.uuid4().hex[:6]}@example.com", workspace="Iota")
    async with AsyncSessionLocal() as session:
        tokens = [row[0] for row in (await session.execute(select(Organization.mcp_token))).all()]
    assert len(tokens) == len(set(tokens))
    assert all(t and len(t) >= 32 for t in tokens)
    assert "dev-mcp-token-meetstream-2026" not in tokens


# ---------------------------------------------------------------------------
# Rate limiting and webhooks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_is_rate_limited():
    async with _client() as c:
        codes = []
        for _ in range(12):
            resp = await c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
            codes.append(resp.status_code)
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]


@pytest.mark.asyncio
async def test_unsigned_webhook_for_unknown_bot_is_ignored(monkeypatch):
    monkeypatch.delenv("MEETSTREAM_WEBHOOK_SECRET", raising=False)
    async with _client() as c:
        resp = await c.post("/api/webhooks/meetstream", json={"bot_id": "never-launched", "event": "bot.failed"})
    assert resp.status_code == 200
    assert resp.json()["reason"] == "unknown_bot"


@pytest.mark.asyncio
async def test_webhook_with_wrong_signature_is_rejected(monkeypatch):
    monkeypatch.setenv("MEETSTREAM_WEBHOOK_SECRET", "a-real-webhook-secret-value")
    async with _client() as c:
        resp = await c.post(
            "/api/webhooks/meetstream",
            content=b'{"bot_id": "x", "event": "bot.failed"}',
            headers={"Content-Type": "application/json", "X-Meetstream-Signature": "sha256=deadbeef"},
        )
    assert resp.status_code == 401


def test_action_item_update_schema_validation():
    update_valid = ActionItemUpdate(status="completed", notes="Sent by Sarah")
    assert update_valid.status == "completed"
    assert update_valid.notes == "Sent by Sarah"
