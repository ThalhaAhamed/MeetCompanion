"""
Meeting Management Endpoints.
Allows creating meetings, triggering MeetStream bot deployment, and retrieving meeting data.
"""
import uuid
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.connection import get_db
from app.database.repositories import MeetingRepository, TranscriptRepository
from app.models.schemas import (
    MeetingCreate, MeetingUpdate, MeetingResponse, MeetingDetailResponse,
    ParticipantResponse, MemoryResponse, ActionItemResponse, TranscriptSegmentResponse
)
from app.services.meetstream import meetstream_client
from app.api.agent import get_active_agent_config_id, _DEFAULT_FIRST_MESSAGE, _require_claimable_agent, get_meetstream_api_key
from app.api.deps import get_current_org_id, get_current_user
from app.models.database import User

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

_SECRET_KEY_PATTERN = ("key", "secret", "token", "password", "authorization")


def _redact_secrets(value):
    """Recursively strip anything that looks like a credential before it leaves our API."""
    if isinstance(value, dict):
        return {
            k: ("***redacted***" if any(p in k.lower() for p in _SECRET_KEY_PATTERN) else _redact_secrets(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    meeting_in: MeetingCreate,
    deploy_bot: bool = Query(default=True, description="Whether to immediately deploy the MeetStream bot"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a meeting and optionally launch a MeetStream bot into the call.
    The meeting record itself is shared workspace-wide (everyone in the
    workspace can see it), but which agent joins as the bot is the launching
    member's own - each person's agent is personal, not shared.
    """
    org_id = user.organization_id
    meeting_repo = MeetingRepository(db)

    # 1. Create meeting record
    meeting = await meeting_repo.create(
        org_id=org_id,
        meeting_url=meeting_in.meeting_url,
        title=meeting_in.title or f"Meeting on {meeting_in.meeting_url.split('/')[-1]}",
        platform=meeting_in.platform,
        customer_name=meeting_in.customer_name,
        project_name=meeting_in.project_name,
        custom_attributes=meeting_in.custom_attributes or {},
        created_by_user_id=user.id,
    )
    await db.commit()
    await db.refresh(meeting)

    # 2. Deploy bot if requested. Each member's own MeetStream API key is
    # required here - bots deploy and bill against the launching member's own
    # MeetStream account, never silently falling back to this deployment's
    # shared key (see require_meetstream_api_key).
    own_meetstream_key = await get_meetstream_api_key(db, user.id)
    if deploy_bot and not own_meetstream_key:
        await meeting_repo.update_status(
            meeting.id,
            processing_error="Add your own MeetStream API key in Agent settings before launching a bot.",
        )
        await db.commit()
        await db.refresh(meeting)
    elif deploy_bot and own_meetstream_key:
        try:
            if meeting_in.agent_config_id:
                # An explicit override still has to be an agent this member
                # actually owns - otherwise the bot's MCP wiring would point
                # at whichever workspace that agent belongs to, leaking that
                # workspace's meeting memory into a call it has no part of.
                await _require_claimable_agent(db, user.id, meeting_in.agent_config_id)
            active_agent_config_id = meeting_in.agent_config_id or await get_active_agent_config_id(db, user.id)

            # The bot's visible in-meeting name must match the name the agent's
            # own system prompt listens for in its ACTIVATION RULE ("only
            # respond when addressed by <AgentName>") - it used to fall back to
            # the free-text meeting title instead, so a meeting titled "Agent P"
            # made the bot show up as "Agent P" while it was still only
            # listening for "MeetStream Companion", and it stayed silent no
            # matter what anyone said. The title field is purely our own
            # dashboard label now; it never reaches MeetStream as bot_name.
            bot_name = "MeetStream Companion"
            if active_agent_config_id:
                try:
                    agent_cfg = await meetstream_client.get_mia_agent(active_agent_config_id, api_key=own_meetstream_key)
                    bot_name = agent_cfg.get("agent_config", agent_cfg).get("AgentName") or bot_name
                except Exception:
                    pass

            # Posted to the meeting chat the instant the bot joins - reliable
            # and independent of the realtime model's own behavior, unlike
            # trying to get the LLM to proactively speak an introduction
            # (which realtime voice agents don't do consistently).
            bot_message = _DEFAULT_FIRST_MESSAGE.format(agent_name=bot_name)

            bot_resp = await meetstream_client.create_bot(
                meeting_link=meeting.meeting_url,
                agent_config_id=active_agent_config_id,
                callback_url=f"{settings.MCP_SERVER_URL.replace('/mcp', '')}/api/webhooks/meetstream",
                bot_message=bot_message,
                custom_attributes={
                    "organization_id": str(org_id),
                    "meeting_id": str(meeting.id),
                    "customer_name": meeting.customer_name,
                    "project_name": meeting.project_name,
                },
                bot_name=bot_name,
                api_key=own_meetstream_key,
            )
            bot_id = bot_resp.get("bot_id") or bot_resp.get("id")
            transcript_id = bot_resp.get("transcript_id")
            if bot_id:
                await meeting_repo.update_status(
                    meeting.id,
                    status="joining",
                    meetstream_transcript_id=transcript_id,
                )
                meeting.meetstream_bot_id = bot_id
                await db.commit()
                await db.refresh(meeting)
        except Exception as e:
            # We don't fail meeting creation if external API fails, but mark status
            print(f"[WARN] MeetStream bot creation failed: {e}")
            await meeting_repo.update_status(
                meeting.id,
                processing_error=f"Failed to launch bot: {str(e)}"
            )
            await db.commit()
            await db.refresh(meeting)

    return meeting


@router.get("", response_model=List[MeetingResponse])
async def list_meetings(
    customer_name: Optional[str] = None,
    project_name: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    day: Optional[date] = Query(None, description="Shortcut for date_from=date_to=day"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """List meetings with optional filtering, including by a single day."""
    if day:
        date_from = date_to = day

    meeting_repo = MeetingRepository(db)
    meetings = await meeting_repo.list_meetings(
        org_id=org_id,
        customer_name=customer_name,
        project_name=project_name,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return meetings


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a meeting record (e.g. one whose bot deployment failed and never
    actually joined a call). Cascades to its participants, transcript segments,
    memories, action items, and vector embeddings."""
    meeting_repo = MeetingRepository(db)
    deleted = await meeting_repo.delete(org_id, meeting_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    await db.commit()


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(
    meeting_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full meeting details including memories and action items."""
    meeting_repo = MeetingRepository(db)
    meeting = await meeting_repo.get_by_id(org_id, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    return MeetingDetailResponse(
        id=meeting.id,
        organization_id=meeting.organization_id,
        meetstream_bot_id=meeting.meetstream_bot_id,
        title=meeting.title,
        meeting_url=meeting.meeting_url,
        platform=meeting.platform,
        customer_name=meeting.customer_name,
        project_name=meeting.project_name,
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        status=meeting.status,
        summary=meeting.summary,
        meetstream_transcript_id=meeting.meetstream_transcript_id,
        processing_status=meeting.processing_status,
        processing_error=meeting.processing_error,
        custom_attributes=meeting.custom_attributes,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        participants=[ParticipantResponse.model_validate(p) for p in meeting.participants],
        memories=[MemoryResponse.model_validate(m) for m in meeting.memories],
        action_items=[ActionItemResponse.model_validate(a) for a in meeting.action_items],
        transcript_segments_count=len(meeting.transcript_segments) if meeting.transcript_segments else 0,
    )


@router.get("/{meeting_id}/transcript", response_model=List[TranscriptSegmentResponse])
async def get_meeting_transcript(
    meeting_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the full ordered transcript for a meeting."""
    meeting_repo = MeetingRepository(db)
    meeting = await meeting_repo.get_by_id(org_id, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    transcript_repo = TranscriptRepository(db)
    segments = await transcript_repo.get_segments_by_meeting(meeting_id)
    return segments


@router.get("/{meeting_id}/bot")
async def get_meeting_bot(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve live bot status/metadata from MeetStream for this meeting."""
    meeting_repo = MeetingRepository(db)
    meeting = await meeting_repo.get_by_id(org_id, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not meeting.meetstream_bot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bot deployed for this meeting")

    # Must use the key the bot was actually created under (the launching
    # member's own, if they had one set), not whoever happens to be asking -
    # a bot created under one MeetStream account can't be queried with a
    # different member's key.
    key_owner_id = meeting.created_by_user_id or user.id
    try:
        bot = await meetstream_client.get_bot(meeting.meetstream_bot_id, api_key=await get_meetstream_api_key(db, key_owner_id))
        return _redact_secrets(bot)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")


@router.post("/{meeting_id}/stop")
async def stop_meeting_bot(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Remove the bot from its meeting (stops recording immediately)."""
    meeting_repo = MeetingRepository(db)
    meeting = await meeting_repo.get_by_id(org_id, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not meeting.meetstream_bot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bot deployed for this meeting")

    key_owner_id = meeting.created_by_user_id or user.id
    try:
        result = await meetstream_client.remove_bot(meeting.meetstream_bot_id, api_key=await get_meetstream_api_key(db, key_owner_id))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MeetStream API error: {e}")

    await meeting_repo.update_status(meeting.id, status="stopped")
    await db.commit()
    return result
