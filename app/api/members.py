"""
Member roster and workspace membership.

Every meeting, memory, and MCP tool call is scoped to a workspace
(Organization) - there's no cross-workspace visibility. Signing up requires
either creating a brand new workspace or joining an existing one via its
join code, so a stranger can no longer land in someone else's data just by
signing up. Adding a teammate from the Members page (while already signed
in) always adds them to your own current workspace, no code needed.
"""
import secrets
import uuid
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import User, Organization
from app.middleware.auth_gate import COOKIE_NAME, decode_session
from app.api.deps import get_current_org_id, get_current_user

router = APIRouter(prefix="/api/members", tags=["members"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def _current_user_id(request: Request, db: AsyncSession) -> "uuid.UUID | None":
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_session(token) if token else None
    if not user_id:
        return None
    result = await db.execute(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_join_code() -> str:
    return secrets.token_hex(4)  # 8 hex chars - short enough to read aloud/type


async def _create_workspace(db: AsyncSession, name: str) -> Organization:
    slug_base = name.strip().lower().replace(" ", "-")[:80] or "workspace"
    slug = slug_base
    suffix = 1
    while (await db.execute(select(Organization.id).where(Organization.slug == slug))).scalar_one_or_none():
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    org = Organization(name=name.strip(), slug=slug, mcp_token=_new_token(), join_code=_new_join_code())
    db.add(org)
    await db.flush()
    return org


class MemberOut(BaseModel):
    id: str
    name: str | None
    email: str


class CreateMemberRequest(BaseModel):
    name: str
    email: str
    password: str
    workspace_name: str | None = None  # create a new workspace (self-signup only)
    join_code: str | None = None       # join an existing workspace (self-signup only)


class UpdateSelfRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None


@router.get("/workspace")
async def get_workspace(org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    """This workspace's name and join code, so a member can invite others."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return {"name": org.name, "join_code": org.join_code}


@router.get("")
async def list_members(org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.organization_id == org_id, User.is_active.is_(True)).order_by(User.created_at)
    )
    return {"members": [MemberOut(id=str(u.id), name=u.name, email=u.email) for u in result.scalars().all()]}


@router.post("")
async def add_member(body: CreateMemberRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    existing = await db.execute(select(User.id).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A member with that email already exists.")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    current_user_id = await _current_user_id(request, db)
    if current_user_id:
        # Already signed in - adding a teammate straight into your own workspace.
        current = (await db.execute(select(User).where(User.id == current_user_id))).scalar_one()
        org_id = current.organization_id
    else:
        # Self-signup - must explicitly create a new workspace or join one by code.
        if bool(body.workspace_name) == bool(body.join_code):
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one of workspace_name (create a new workspace) or join_code (join an existing one).",
            )
        if body.workspace_name:
            org = await _create_workspace(db, body.workspace_name)
            org_id = org.id
        else:
            result = await db.execute(select(Organization.id).where(Organization.join_code == body.join_code.strip()))
            org_id = result.scalar_one_or_none()
            if not org_id:
                raise HTTPException(status_code=404, detail="No workspace found with that join code.")

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
async def update_self(body: UpdateSelfRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if body.email is not None:
        email = body.email.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise HTTPException(status_code=400, detail="Invalid email address.")
        existing = await db.execute(select(User.id).where(User.email == email, User.id != user.id))
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
async def remove_member(member_id: str, org_id: uuid.UUID = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    try:
        target_id = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member id")

    count_result = await db.execute(
        select(func.count()).select_from(User).where(User.organization_id == org_id, User.is_active.is_(True))
    )
    if count_result.scalar_one() <= 1:
        raise HTTPException(status_code=400, detail="Can't remove the last remaining member.")

    result = await db.execute(
        select(User).where(User.id == target_id, User.organization_id == org_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found.")

    # Hard delete, not a soft is_active=False flag: the (organization_id, email)
    # DB constraint means a deactivated-but-still-present row permanently blocks
    # that email from ever signing up again in this workspace, which is
    # confusing ("that email is already a member" for an email nobody can
    # actually use). A removed member should just be gone.
    await db.delete(user)
    await db.commit()
    return {"removed": True}
