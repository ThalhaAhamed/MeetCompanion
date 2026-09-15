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
from typing import Any, Dict

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import Membership, Organization, User
from app.middleware.auth_gate import COOKIE_NAME, decode_session
from app.api.deps import OWNER, get_current_org_id, get_current_user, is_owner, require_owner
from app import permissions as perms
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
async def get_workspace(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    This workspace's name, and its join code for anyone allowed to invite.
    Everyone also gets the member permissions in effect, so the UI can show
    what applies; only an owner may change them (see PUT /workspace/permissions).
    """
    org = await perms.load_org(user.organization_id, db)
    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    mine = perms.effective_permissions(user, org)
    return {
        "name": org.name,
        "join_code": org.join_code if mine["invite_members"] else None,
        "member_permissions": perms.member_permissions(org),
        "permissions": perms.describe(),
    }


class PermissionsUpdate(BaseModel):
    member_permissions: dict[str, bool]


@router.put("/workspace/permissions")
async def set_workspace_permissions(
    body: PermissionsUpdate, owner: User = Depends(require_owner), db: AsyncSession = Depends(get_db)
):
    """What members of this workspace may do. Owner-only; owners are never restricted."""
    unknown = sorted(set(body.member_permissions) - perms.PERMISSION_KEYS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission: {', '.join(unknown)}")
    org = await perms.load_org(owner.organization_id, db)
    if not org:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    current = perms.member_permissions(org)
    current.update({k: bool(v) for k, v in body.member_permissions.items()})
    # Reassign rather than mutate: the JSON column only notices a new value.
    org.settings = {**(org.settings or {}), "permissions": current}
    await db.commit()
    return {"member_permissions": perms.member_permissions(org)}


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
        # Already signed in - adding a teammate straight into your own workspace,
        # which is inviting, so it needs the same permission the join code does.
        current = (await db.execute(select(User).where(User.id == current_user_id))).scalar_one()
        org_id = current.organization_id
        if not perms.effective_permissions(current, await perms.load_org(org_id, db))["invite_members"]:
            raise HTTPException(
                status_code=403,
                detail="Members of this workspace cannot invite people. A workspace owner can change that from the Members page.",
            )
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
        await db.flush()
        # The membership is what actually grants access; organization_id on the
        # user is only the workspace they are currently looking at.
        db.add(Membership(user_id=user.id, organization_id=org_id, role=role))
        await db.commit()
    except IntegrityError:
        # Two sign-ups for the same address raced; the database kept one.
        await db.rollback()
        raise HTTPException(status_code=409, detail="A member with that email already exists.")
    return MemberOut(id=str(user.id), name=user.name, email=user.email, role=user.role)


# ---------------------------------------------------------------------------
# Workspaces a person belongs to, and which one they are looking at
# ---------------------------------------------------------------------------


class WorkspaceOut(BaseModel):
    id: str
    name: str
    role: str
    is_active: bool


@router.get("/workspaces")
async def list_my_workspaces(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Every workspace this account belongs to, flagging the current one."""
    rows = (
        await db.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(Membership.user_id == user.id)
            .order_by(Organization.name)
        )
    ).all()
    return {
        "workspaces": [
            WorkspaceOut(
                id=str(org.id),
                name=org.name,
                role=membership.role,
                is_active=org.id == user.organization_id,
            ).model_dump()
            for membership, org in rows
        ]
    }


class CreateWorkspaceRequest(BaseModel):
    name: str
    activate: bool = True


@router.post("/workspaces")
async def create_workspace_for_me(
    body: CreateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Start another workspace under the account already signed in.

    The counterpart to joining by code: without this you could only ever end up
    in a second workspace by being invited to one, which makes switching
    useless for the person who wants to keep, say, personal notes apart from a
    client's. Creating one makes you its owner, exactly as at sign-up.
    """
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A workspace name is required.")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="That workspace name is too long.")

    org = await _create_workspace(db, name)
    db.add(Membership(user_id=user.id, organization_id=org.id, role=OWNER))
    if body.activate:
        user.organization_id = org.id
        user.role = OWNER
    await db.commit()
    return {"id": str(org.id), "name": org.name, "role": OWNER, "activated": body.activate}


class JoinWorkspaceRequest(BaseModel):
    join_code: str
    activate: bool = True


@router.post("/workspaces/join")
async def join_workspace(
    body: JoinWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Add the signed-in account to another workspace using its join code.

    Distinct from sign-up, which also takes a join code but makes a *new*
    account: this adds a membership to the account you are already using, so
    one person can hold several workspaces and switch between them rather than
    juggling a login per workspace.
    """
    code = (body.join_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="A join code is required.")

    org = (
        await db.execute(select(Organization).where(Organization.join_code == code))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="No workspace found with that join code.")

    existing = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.organization_id == org.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        # Joining by code never confers ownership - that belongs to whoever
        # created the workspace.
        db.add(Membership(user_id=user.id, organization_id=org.id, role="member"))
        try:
            await db.flush()
        except IntegrityError:
            # Someone double-clicked; the membership they already have is fine.
            await db.rollback()
            raise HTTPException(status_code=409, detail="You are already a member of that workspace.")
        role = "member"
    else:
        role = existing.role

    if body.activate:
        user.organization_id = org.id
        user.role = role
    await db.commit()
    return {
        "id": str(org.id),
        "name": org.name,
        "role": role,
        "activated": body.activate,
        "already_member": existing is not None,
    }


@router.post("/workspaces/{organization_id}/activate")
async def activate_workspace(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Switch which workspace this account is looking at.

    Only a workspace the caller is actually a member of - otherwise pointing
    organization_id at someone else's workspace would hand over all of its
    data, since every org-scoped query trusts that column.
    """
    membership = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="You are not a member of that workspace.")

    user.organization_id = organization_id
    # Role travels with the workspace: owner of one says nothing about another.
    user.role = membership.role
    await db.commit()
    return {"active_workspace": str(organization_id), "role": membership.role}


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
