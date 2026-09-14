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
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import User, Organization
from app.middleware.auth_gate import COOKIE_NAME, decode_session
from app.api.deps import OWNER, get_current_org_id, get_current_user, is_owner, require_owner
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/members", tags=["members"])


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
    """
    Insert the workspace with a unique slug.

    The check-then-insert on the slug can lose a race between two sign-ups
    with the same workspace name; the unique index then rejects the second
    insert. Rather than surface that as a 500, retry with the next suffix
    a few times - and if the slug space is that contended, fall back to a
    random one.
    """
    slug_base = name.strip().lower().replace(" ", "-")[:80] or "workspace"
    slug = slug_base
    suffix = 1
    while (await db.execute(select(Organization.id).where(Organization.slug == slug))).scalar_one_or_none():
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    # Nothing else has been written in this session yet (the workspace is
    # the first insert of a sign-up), so a full rollback loses nothing.
    for attempt in range(5):
        org = Organization(name=name.strip(), slug=slug, mcp_token=_new_token(), join_code=_new_join_code())
        db.add(org)
        try:
            await db.flush()
            return org
        except IntegrityError:
            await db.rollback()
            suffix += 1
            slug = f"{slug_base}-{suffix}" if attempt < 3 else f"{slug_base}-{secrets.token_hex(3)}"
    raise HTTPException(status_code=409, detail="Could not allocate a workspace name; please try again.")


class MemberOut(BaseModel):
    id: str
    name: str | None
    email: str
    role: str = "member"


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
    return {"members": [MemberOut(id=str(u.id), name=u.name, email=u.email, role=u.role) for u in result.scalars().all()]}


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

    role = "member"
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
            # Whoever creates a workspace owns it.
            role = OWNER
        else:
            result = await db.execute(select(Organization.id).where(Organization.join_code == body.join_code.strip()))
            org_id = result.scalar_one_or_none()
            if not org_id:
                raise HTTPException(status_code=404, detail="No workspace found with that join code.")

    user = User(
        organization_id=org_id,
        email=email,
        name=body.name.strip(),
        password_hash=hash_password(body.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Two sign-ups for the same address raced; the database kept one.
        await db.rollback()
        raise HTTPException(status_code=409, detail="A member with that email already exists.")
    return MemberOut(id=str(user.id), name=user.name, email=user.email, role=user.role)


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
        user.password_hash = hash_password(body.password)

    await db.commit()
    return MemberOut(id=str(user.id), name=user.name, email=user.email, role=user.role)


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/{member_id}/reset-password")
async def reset_member_password(
    member_id: str,
    body: ResetPasswordRequest,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    "Forgot password" without an email service: a workspace owner can set a
    new password for a teammate. Not self-service, but works with no
    email-sending integration to wire up.
    """
    org_id = owner.organization_id
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    try:
        target_id = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member id")

    result = await db.execute(
        select(User).where(User.id == target_id, User.organization_id == org_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found.")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"reset": True}


class RoleRequest(BaseModel):
    role: str


@router.post("/{member_id}/role")
async def set_member_role(
    member_id: str,
    body: RoleRequest,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Promote a teammate to owner or demote them to member. A workspace always keeps at least one owner."""
    if body.role not in (OWNER, "member"):
        raise HTTPException(status_code=400, detail="Role must be 'owner' or 'member'.")
    try:
        target_id = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member id")
    result = await db.execute(
        select(User).where(User.id == target_id, User.organization_id == owner.organization_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found.")
    if body.role != OWNER and user.role == OWNER and await _owner_count(db, owner.organization_id) <= 1:
        raise HTTPException(status_code=400, detail="A workspace needs at least one owner.")
    user.role = body.role
    await db.commit()
    return MemberOut(id=str(user.id), name=user.name, email=user.email, role=user.role)


async def _owner_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(User).where(
            User.organization_id == org_id, User.role == OWNER, User.is_active.is_(True)
        )
    )
    return result.scalar_one()


@router.delete("/{member_id}")
async def remove_member(member_id: str, current: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Owners can remove anyone; a member can only remove themselves."""
    org_id = current.organization_id
    try:
        target_id = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not is_owner(current) and target_id != current.id:
        raise HTTPException(status_code=403, detail="Only a workspace owner can remove other members.")

    result = await db.execute(
        select(User).where(User.id == target_id, User.organization_id == org_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found.")

    count_result = await db.execute(
        select(func.count()).select_from(User).where(User.organization_id == org_id, User.is_active.is_(True))
    )
    if count_result.scalar_one() <= 1:
        raise HTTPException(status_code=400, detail="Can't remove the last remaining member.")
    if user.role == OWNER and await _owner_count(db, org_id) <= 1:
        raise HTTPException(status_code=400, detail="Promote another member to owner before removing the last one.")

    # Hard delete, not a soft is_active=False flag: the (organization_id, email)
    # DB constraint means a deactivated-but-still-present row permanently blocks
    # that email from ever signing up again in this workspace, which is
    # confusing ("that email is already a member" for an email nobody can
    # actually use). A removed member should just be gone.
    await db.delete(user)
    await db.commit()
    return {"removed": True}
