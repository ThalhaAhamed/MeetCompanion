"""
Signing in with the machine's device key.

The desktop app presents a secret only a local process can read, so the person
who installed it is not asked for a password every launch. What matters is that
it is a *sign-in*, not a bypass: a wrong key, a missing key, or an ambiguous
"which owner?" must all still get 401.
"""
import uuid

import pytest
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.middleware.auth_gate import COOKIE_NAME, DEVICE_COOKIE_NAME
from app.models.database import Membership, Organization, User
from app.secrets import device_secret
from app.security import hash_password


async def _make_owner(email: str, org_id=None):
    org_id = org_id or uuid.uuid4()
    async with AsyncSessionLocal() as session:
        if not (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none():
            session.add(Organization(id=org_id, name=f"W-{org_id.hex[:6]}", slug=f"w-{org_id.hex[:6]}",
                                     mcp_token=uuid.uuid4().hex, join_code=uuid.uuid4().hex[:8]))
        user = User(id=uuid.uuid4(), organization_id=org_id, email=email, name=email,
                    role="owner", is_active=True, settings={},
                    password_hash=hash_password("SomePassword123"))
        session.add(user)
        await session.flush()
        session.add(Membership(user_id=user.id, organization_id=org_id, role="owner"))
        await session.commit()
        return user.id


@pytest.mark.asyncio
async def test_no_cookies_at_all_is_still_refused(client):
    assert (await client.get("/api/notebook/notes")).status_code == 401


@pytest.mark.asyncio
async def test_device_key_signs_in_the_sole_owner(client):
    await _make_owner("solo@device.test")
    r = await client.get("/api/notebook/notes", headers={"Cookie": f"{DEVICE_COOKIE_NAME}={device_secret()}"})
    assert r.status_code == 200, r.text
    # It issues a real session rather than waving the request through.
    assert COOKIE_NAME in r.cookies


@pytest.mark.asyncio
async def test_a_wrong_device_key_is_refused(client):
    await _make_owner("solo2@device.test")
    r = await client.get("/api/notebook/notes", headers={"Cookie": f"{DEVICE_COOKIE_NAME}=not-the-real-key"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_device_key_refuses_when_several_owners_exist(client):
    """On a shared workspace 'the local user' is ambiguous - do not guess."""
    org = uuid.uuid4()
    await _make_owner("one@device.test", org)
    await _make_owner("two@device.test", org)
    r = await client.get("/api/notebook/notes", headers={"Cookie": f"{DEVICE_COOKIE_NAME}={device_secret()}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_device_key_does_not_resurrect_a_deactivated_owner(client):
    user_id = await _make_owner("gone@device.test")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        user.is_active = False
        await session.commit()
    r = await client.get("/api/notebook/notes", headers={"Cookie": f"{DEVICE_COOKIE_NAME}={device_secret()}"})
    assert r.status_code == 401
