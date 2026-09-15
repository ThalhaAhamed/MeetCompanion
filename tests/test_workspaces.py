"""
Belonging to more than one workspace, and switching between them.

The switch rewrites User.organization_id, which every org-scoped query trusts -
so the cases that matter are that you only ever land in a workspace you are
actually a member of, and that what you can see changes with it.
"""
import uuid

import pytest
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.models.database import Membership, Organization, User
from app.security import hash_password


async def _workspaces(client):
    r = await client.get("/api/members/workspaces")
    assert r.status_code == 200, r.text
    return r.json()["workspaces"]


async def _second_workspace(client, name="Second"):
    """A workspace the signed-in user can join, created independently."""
    org_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        session.add(Organization(id=org_id, name=name, slug=f"s-{org_id.hex[:8]}",
                                 mcp_token=uuid.uuid4().hex, join_code=uuid.uuid4().hex[:8]))
        await session.commit()
        code = (await session.execute(
            select(Organization.join_code).where(Organization.id == org_id))).scalar_one()
    return org_id, code


@pytest.mark.asyncio
async def test_signup_creates_a_membership(authed_client):
    me = (await authed_client.get("/api/auth/check")).json()["member"]
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Membership).where(Membership.user_id == uuid.UUID(me["id"])))).scalars().all()
    assert len(rows) == 1, "every account needs a membership, or it belongs nowhere"
    assert str(rows[0].organization_id)


@pytest.mark.asyncio
async def test_lists_only_my_workspaces_and_flags_the_active_one(authed_client):
    mine = await _workspaces(authed_client)
    assert len(mine) == 1 and mine[0]["is_active"] is True

    # A workspace that exists but that I am not in must not appear.
    await _second_workspace(authed_client, "Not Mine")
    assert [w["name"] for w in await _workspaces(authed_client)] == [mine[0]["name"]]


@pytest.mark.asyncio
async def test_cannot_activate_a_workspace_i_do_not_belong_to(authed_client):
    other_id, _ = await _second_workspace(authed_client, "Theirs")
    before = (await authed_client.get("/api/auth/check")).json()["member"]

    r = await authed_client.post(f"/api/members/workspaces/{other_id}/activate")
    assert r.status_code == 404, "activating a stranger's workspace would hand over its data"

    after = (await authed_client.get("/api/auth/check")).json()["member"]
    assert after == before


@pytest.mark.asyncio
async def test_switching_changes_what_i_can_see(authed_client):
    """Notes written in one workspace must not follow me into the other."""
    first = (await _workspaces(authed_client))[0]
    await authed_client.post("/api/notebook/notes", json={"title": "First-only note"})

    # Join a second workspace as the same account.
    other_id, code = await _second_workspace(authed_client, "Second")
    me = (await authed_client.get("/api/auth/check")).json()["member"]
    async with AsyncSessionLocal() as session:
        session.add(Membership(user_id=uuid.UUID(me["id"]), organization_id=other_id, role="member"))
        await session.commit()

    assert {w["name"] for w in await _workspaces(authed_client)} == {first["name"], "Second"}

    r = await authed_client.post(f"/api/members/workspaces/{other_id}/activate")
    assert r.status_code == 200 and r.json()["role"] == "member"

    titles = [n["title"] for n in (await authed_client.get("/api/notebook/notes")).json()["notes"]]
    assert "First-only note" not in titles, "switching must not leak the other workspace's notes"

    # ...and switching back brings it into view again.
    await authed_client.post(f"/api/members/workspaces/{first['id']}/activate")
    titles = [n["title"] for n in (await authed_client.get("/api/notebook/notes")).json()["notes"]]
    assert "First-only note" in titles


@pytest.mark.asyncio
async def test_role_follows_the_workspace(authed_client):
    """Owner of one workspace, member of another - the role must travel."""
    first = (await _workspaces(authed_client))[0]
    assert first["role"] == "owner"

    other_id, _ = await _second_workspace(authed_client, "Guest space")
    me = (await authed_client.get("/api/auth/check")).json()["member"]
    async with AsyncSessionLocal() as session:
        session.add(Membership(user_id=uuid.UUID(me["id"]), organization_id=other_id, role="member"))
        await session.commit()

    await authed_client.post(f"/api/members/workspaces/{other_id}/activate")
    assert (await authed_client.get("/api/auth/check")).json()["member"]["role"] == "member"
    # An owner-only action must now be refused. (Deliberately not a /api/setup
    # route: those open up when the app is unconfigured, which other tests
    # change underneath us.)
    refused = await authed_client.put("/api/agent/write-tools", json={"enabled": False})
    assert refused.status_code == 403, refused.text

    await authed_client.post(f"/api/members/workspaces/{first['id']}/activate")
    assert (await authed_client.get("/api/auth/check")).json()["member"]["role"] == "owner"


@pytest.mark.asyncio
async def test_workspace_endpoints_need_a_session(client):
    assert (await client.get("/api/members/workspaces")).status_code == 401
    assert (await client.post(f"/api/members/workspaces/{uuid.uuid4()}/activate")).status_code == 401


@pytest.mark.asyncio
async def test_join_another_workspace_with_a_code_keeps_one_account(authed_client):
    """Joining by code must extend this account, not create a second one."""
    me = (await authed_client.get("/api/auth/check")).json()["member"]
    other_id, code = await _second_workspace(authed_client, "Invited")

    r = await authed_client.post("/api/members/workspaces/join", json={"join_code": code})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Invited" and r.json()["role"] == "member"

    # Same account, now in two workspaces, looking at the new one.
    assert (await authed_client.get("/api/auth/check")).json()["member"]["id"] == me["id"]
    names = {w["name"] for w in await _workspaces(authed_client)}
    assert len(names) == 2 and "Invited" in names
    assert next(w for w in await _workspaces(authed_client) if w["is_active"])["name"] == "Invited"


@pytest.mark.asyncio
async def test_joining_by_code_never_grants_ownership(authed_client):
    _, code = await _second_workspace(authed_client, "Someone else's")
    r = await authed_client.post("/api/members/workspaces/join", json={"join_code": code})
    assert r.json()["role"] == "member"
    assert (await authed_client.get("/api/auth/check")).json()["member"]["role"] == "member"


@pytest.mark.asyncio
async def test_bad_and_repeated_join_codes(authed_client):
    assert (await authed_client.post("/api/members/workspaces/join",
                                     json={"join_code": "nope"})).status_code == 404
    assert (await authed_client.post("/api/members/workspaces/join",
                                     json={"join_code": "  "})).status_code == 400

    _, code = await _second_workspace(authed_client, "Twice")
    first = await authed_client.post("/api/members/workspaces/join", json={"join_code": code})
    again = await authed_client.post("/api/members/workspaces/join", json={"join_code": code})
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["already_member"] is True
    # Still exactly one membership for it.
    assert len([w for w in await _workspaces(authed_client) if w["name"] == "Twice"]) == 1


@pytest.mark.asyncio
async def test_join_requires_a_session(client):
    r = await client.post("/api/members/workspaces/join", json={"join_code": "x"})
    assert r.status_code == 401
