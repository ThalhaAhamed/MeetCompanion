"""
Action Item Endpoints.
Allows the dashboard to update action item status/owner/notes directly.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.database.repositories import ActionItemRepository
from app.models.schemas import ActionItemUpdate, ActionItemResponse
from app.api.deps import get_current_org_id

router = APIRouter(prefix="/api/action-items", tags=["action-items"])


@router.patch("/{action_id}", response_model=ActionItemResponse)
async def update_action_item(
    action_id: uuid.UUID,
    update_in: ActionItemUpdate,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Update an action item's status, owner, due date, priority, or notes."""
    action_repo = ActionItemRepository(db)
    action = await action_repo.update(org_id, action_id, update_in)
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    await db.commit()
    await db.refresh(action)
    return action
