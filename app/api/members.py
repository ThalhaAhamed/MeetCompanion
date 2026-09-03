"""
Member roster: add/remove the people who can sign into the hub.

There's no self-serve signup - every request here (list, add, remove)
requires an active member session. New members are added by an
already-logged-in member from the Members page.
"""
import uuid
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.connection import get_db
from app.models.database import User, Organization
from app.middleware.auth_gate import COOKIE_NAME, decode_session

router = APIRouter(prefix="/api/members", tags=["members"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def _current_user_id(request: Request, db: AsyncSession) -> "uuid.UUID | None":
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_session(token) if token else None
    if not user_id:
        return None
    result = await db.execute(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def _org_id(db: AsyncSession) -> uuid.UUID:
    org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
    existing = await db.execute(select(Organization.id).where(Organization.id == org_id))
    if existing.scalar_one_or_none():
        return org_id
    db.add(Organization(id=org_id, name=settings.APP_NAME, slug="default"))
    await db.flush()
    return org_id


class MemberOut(BaseModel):
    id: str
    name: str | None
    email: str


class CreateMemberRequest(BaseModel):
    name: str
    email: str
    password: str


class UpdateSelfRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None


@router.get("")
async def list_members(request: Request, db: AsyncSession = Depends(get_db)):
    if not await _current_user_id(request, db):
        raise HTTPException(status_code=401, detail="Sign in required.")
    result = await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.created_at))
    return {"members": [MemberOut(id=str(u.id), name=u.name, email=u.email) for u in result.scalars().all()]}


@router.post("")
async def add_member(body: CreateMemberRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not await _current_user_id(request, db):
        raise HTTPException(status_code=401, detail="Sign in required.")

    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    existing = await db.execute(select(User.id).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A member with that email already exists.")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    org_id = await _org_id(db)
    user = User(
        organization_id=org_id,
        email=email,
        name=body.name.strip(),
        password_hash=pwd_context.hash(body.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return MemberOut(id=str(user.id), name=user.name, email=user.email)


@router.patch("/me")
async def update_self(body: UpdateSelfRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = await _current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required.")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    if body.email is not None:
        email = body.email.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(status_code=400, detail="Invalid email address.")
        existing = await db.execute(select(User.id).where(User.email == email, User.id != user_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A member with that email already exists.")
        user.email = email

    if body.name is not None:
        user.name = body.name.strip()

    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
        user.password_hash = pwd_context.hash(body.password)

    await db.commit()
    return MemberOut(id=str(user.id), name=user.name, email=user.email)


@router.delete("/{member_id}")
async def remove_member(member_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    if not await _current_user_id(request, db):
        raise HTTPException(status_code=401, detail="Sign in required.")

    try:
        target_id = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member id")

    count_result = await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    if count_result.scalar_one() <= 1:
        raise HTTPException(status_code=400, detail="Can't remove the last remaining member.")

    result = await db.execute(select(User).where(User.id == target_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found.")

    user.is_active = False
    await db.commit()
    return {"removed": True}
