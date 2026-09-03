"""
One-off bootstrap: create the very first member account.

There's no self-serve signup and no shared-passphrase fallback - add_member
always requires an existing session, so a brand-new deployment with zero
members has no way to get in through the UI at all. Run this once against
the target database (locally with DATABASE_URL pointed at it, or via
`railway run` against a deployed one) to create that first account, then use
the Members page for everyone after.

Usage:
    python scripts/create_first_member.py "Your Name" you@example.com yourpassword
"""
import asyncio
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from passlib.context import CryptContext
from sqlalchemy import select
from app.config import settings
from app.database.connection import AsyncSessionLocal
from app.models.database import User, Organization

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_first_member.py \"Your Name\" you@example.com yourpassword")
        sys.exit(1)

    name, email, password = sys.argv[1], sys.argv[2].strip().lower(), sys.argv[3]
    if len(password) < 8:
        print("[ERROR] Password must be at least 8 characters.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
        org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
        if not org:
            db.add(Organization(id=org_id, name=settings.APP_NAME, slug="default"))
            await db.flush()

        existing = (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
        if existing:
            print(f"[ERROR] A member with email {email} already exists.")
            sys.exit(1)

        user = User(
            organization_id=org_id,
            email=email,
            name=name,
            password_hash=pwd_context.hash(password),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"[OK] Created member {name} <{email}>. Sign in at your frontend URL.")


if __name__ == "__main__":
    asyncio.run(main())
