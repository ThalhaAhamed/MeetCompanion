"""
Data access repositories with strict organization isolation.
"""
import uuid
from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.database import (
    Organization, Meeting, Participant, TranscriptSegment,
    Memory, MemoryType, ActionItem, MeetingMemoryEmbedding,
    CompanyKnowledgeEmbedding, WebhookEvent, ProcessingJob
)
from app.models.schemas import (
    MeetingCreate, MeetingUpdate, MemoryCreate, ActionItemCreate, ActionItemUpdate
)


class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, org_id: uuid.UUID) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, name: str, slug: str, settings: Optional[Dict[str, Any]] = None) -> Organization:
        org = Organization(name=name, slug=slug, settings=settings or {})
        self.session.add(org)
        await self.session.flush()
        return org

    async def update_settings(self, org_id: uuid.UUID, patch: Dict[str, Any]) -> Optional[Organization]:
        """Merge `patch` into the org's settings JSONB (shallow merge, one level)."""
        org = await self.get_by_id(org_id)
        if not org:
            return None
        org.settings = {**(org.settings or {}), **patch}
        await self.session.flush()
        return org


class MeetingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, org_id: uuid.UUID, meeting_id: uuid.UUID) -> Optional[Meeting]:
        stmt = (
            select(Meeting)
            .where(and_(Meeting.organization_id == org_id, Meeting.id == meeting_id))
            .options(
                selectinload(Meeting.participants),
                selectinload(Meeting.memories),
                selectinload(Meeting.action_items),
                selectinload(Meeting.transcript_segments),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_title(self, org_id: uuid.UUID, title: str) -> Optional[Meeting]:
        """Most recent meeting whose title contains the given text (case-insensitive)."""
        stmt = (
            select(Meeting)
            .where(and_(Meeting.organization_id == org_id, Meeting.title.ilike(f"%{title}%")))
            .options(
                selectinload(Meeting.participants),
                selectinload(Meeting.memories),
                selectinload(Meeting.action_items),
                selectinload(Meeting.transcript_segments),
            )
            .order_by(desc(Meeting.started_at), desc(Meeting.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_unscoped(self, meeting_id: uuid.UUID) -> Optional[Meeting]:
        """Like get_by_id but without an org filter - for contexts (webhooks,
        background processing) that only have a meeting_id and don't yet know
        which workspace it belongs to; the caller reads it off the returned
        row (meeting.organization_id) instead."""
        stmt = (
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(
                selectinload(Meeting.participants),
                selectinload(Meeting.memories),
                selectinload(Meeting.action_items),
                selectinload(Meeting.transcript_segments),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_bot_id(self, bot_id: str) -> Optional[Meeting]:
        stmt = select(Meeting).where(Meeting.meetstream_bot_id == bot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_transcript_id(self, transcript_id: str) -> Optional[Meeting]:
        stmt = select(Meeting).where(Meeting.meetstream_transcript_id == transcript_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_meetings(
        self,
        org_id: uuid.UUID,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Meeting]:
        conditions = [Meeting.organization_id == org_id]
        if customer_name:
            conditions.append(func.lower(Meeting.customer_name) == customer_name.lower())
        if project_name:
            conditions.append(func.lower(Meeting.project_name) == project_name.lower())
        if status:
            conditions.append(Meeting.status == status)
        effective_date = func.coalesce(Meeting.started_at, Meeting.created_at)
        if date_from:
            conditions.append(effective_date >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
        if date_to:
            conditions.append(effective_date <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))

        stmt = (
            select(Meeting)
            .where(and_(*conditions))
            .order_by(desc(Meeting.started_at), desc(Meeting.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, org_id: uuid.UUID, meeting_id: uuid.UUID) -> bool:
        """Delete a meeting and everything cascading from it (participants, segments,
        memories, action items, processing jobs). Does not remove vector embeddings
        or its bot on MeetStream - callers handle those separately if needed."""
        meeting = await self.get_by_id(org_id, meeting_id)
        if not meeting:
            return False
        await self.session.delete(meeting)
        await self.session.flush()
        return True

    async def count_meetings(
        self,
        org_id: uuid.UUID,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> int:
        """True total count matching the same filters as list_meetings, ignoring limit/offset."""
        conditions = [Meeting.organization_id == org_id]
        if customer_name:
            conditions.append(func.lower(Meeting.customer_name) == customer_name.lower())
        if project_name:
            conditions.append(func.lower(Meeting.project_name) == project_name.lower())
        if status:
            conditions.append(Meeting.status == status)
        effective_date = func.coalesce(Meeting.started_at, Meeting.created_at)
        if date_from:
            conditions.append(effective_date >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
        if date_to:
            conditions.append(effective_date <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))

        stmt = select(func.count(Meeting.id)).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(
        self,
        org_id: uuid.UUID,
        meeting_url: Optional[str] = None,
        title: Optional[str] = None,
        platform: Optional[str] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        meetstream_bot_id: Optional[str] = None,
        custom_attributes: Optional[Dict[str, Any]] = None,
    ) -> Meeting:
        meeting = Meeting(
            organization_id=org_id,
            meeting_url=meeting_url,
            title=title,
            platform=platform,
            customer_name=customer_name,
            project_name=project_name,
            meetstream_bot_id=meetstream_bot_id,
            custom_attributes=custom_attributes or {},
            status="pending",
            processing_status="pending",
        )
        self.session.add(meeting)
        await self.session.flush()
        return meeting

    async def update_status(
        self,
        meeting_id: uuid.UUID,
        status: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        meetstream_transcript_id: Optional[str] = None,
        summary: Optional[str] = None,
        processing_status: Optional[str] = None,
        processing_error: Optional[str] = None,
    ) -> Optional[Meeting]:
        stmt = select(Meeting).where(Meeting.id == meeting_id)
        result = await self.session.execute(stmt)
        meeting = result.scalar_one_or_none()
        if not meeting:
            return None

        if status is not None:
            meeting.status = status
        if started_at is not None:
            meeting.started_at = started_at
        if ended_at is not None:
            meeting.ended_at = ended_at
        if meetstream_transcript_id is not None:
            meeting.meetstream_transcript_id = meetstream_transcript_id
        if summary is not None:
            meeting.summary = summary
        if processing_status is not None:
            meeting.processing_status = processing_status
        if processing_error is not None:
            meeting.processing_error = processing_error

        await self.session.flush()
        return meeting


class ParticipantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def sync_from_speaker_names(self, meeting_id: uuid.UUID, speaker_names: List[str]) -> List[Participant]:
        """
        Ensure one Participant row exists per distinct real speaker name seen in a
        meeting's transcript. Transcript ingestion only ever populates the speaker
        string on TranscriptSegment - nothing wrote to the participants table, so
        every meeting showed zero participants regardless of who was in the call.
        Skips generic/unknown placeholders that don't identify a real person.
        """
        distinct_names = {
            name.strip() for name in speaker_names
            if name and name.strip() and name.strip().lower() not in ("unknown", "speaker")
        }
        if not distinct_names:
            return []

        existing_stmt = select(Participant.name).where(Participant.meeting_id == meeting_id)
        existing = {row[0] for row in (await self.session.execute(existing_stmt)).all()}

        new_participants = []
        for name in distinct_names - existing:
            participant = Participant(meeting_id=meeting_id, name=name)
            self.session.add(participant)
            new_participants.append(participant)

        if new_participants:
            await self.session.flush()
        return new_participants


class TranscriptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_segments(self, meeting_id: uuid.UUID, segments_data: List[Dict[str, Any]]) -> List[TranscriptSegment]:
        segments = []
        for i, data in enumerate(segments_data):
            seg = TranscriptSegment(
                meeting_id=meeting_id,
                speaker=data.get("speaker"),
                speaker_identifier=data.get("speaker_identifier"),
                text=data["text"],
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                confidence=data.get("confidence"),
                word_data=data.get("word_data"),
                segment_index=data.get("segment_index", i),
            )
            segments.append(seg)
            self.session.add(seg)
        await self.session.flush()
        return segments

    async def get_segments_by_meeting(self, meeting_id: uuid.UUID) -> List[TranscriptSegment]:
        stmt = (
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.segment_index, TranscriptSegment.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        org_id: uuid.UUID,
        meeting_id: uuid.UUID,
        memory_type: MemoryType,
        content: str,
        importance: int = 5,
        speaker: Optional[str] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        source_segment_ids: Optional[List[uuid.UUID]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        mem = Memory(
            organization_id=org_id,
            meeting_id=meeting_id,
            type=memory_type,
            content=content,
            importance=importance,
            speaker=speaker,
            customer_name=customer_name,
            project_name=project_name,
            source_segment_ids=source_segment_ids,
            metadata_=metadata or {},
        )
        self.session.add(mem)
        await self.session.flush()
        return mem

    async def create_batch(self, org_id: uuid.UUID, meeting_id: uuid.UUID, memories_data: List[Dict[str, Any]]) -> List[Memory]:
        created = []
        for data in memories_data:
            m_type = data["type"]
            if isinstance(m_type, str):
                m_type = MemoryType(m_type)
            mem = Memory(
                organization_id=org_id,
                meeting_id=meeting_id,
                type=m_type,
                content=data["content"],
                importance=data.get("importance", 5),
                speaker=data.get("speaker"),
                customer_name=data.get("customer_name"),
                project_name=data.get("project_name"),
                source_segment_ids=data.get("source_segment_ids"),
                metadata_=data.get("metadata", {}),
            )
            self.session.add(mem)
            created.append(mem)
        await self.session.flush()
        return created

    async def list_memories(
        self,
        org_id: uuid.UUID,
        meeting_id: Optional[uuid.UUID] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        speaker: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 50,
    ) -> List[Memory]:
        conditions = [Memory.organization_id == org_id]
        if meeting_id:
            conditions.append(Memory.meeting_id == meeting_id)
        if customer_name:
            conditions.append(func.lower(Memory.customer_name) == customer_name.lower())
        if project_name:
            conditions.append(func.lower(Memory.project_name) == project_name.lower())
        if speaker:
            conditions.append(func.lower(Memory.speaker) == speaker.lower())
        if memory_type:
            conditions.append(Memory.type == memory_type)

        stmt = select(Memory).where(and_(*conditions)).order_by(desc(Memory.importance), desc(Memory.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ActionItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        org_id: uuid.UUID,
        meeting_id: uuid.UUID,
        task: str,
        memory_id: Optional[uuid.UUID] = None,
        owner: Optional[str] = None,
        due_date: Optional[date] = None,
        status: str = "open",
        priority: str = "medium",
        notes: Optional[str] = None,
    ) -> ActionItem:
        action = ActionItem(
            organization_id=org_id,
            meeting_id=meeting_id,
            memory_id=memory_id,
            task=task,
            owner=owner,
            due_date=due_date,
            status=status,
            priority=priority,
            notes=notes,
        )
        self.session.add(action)
        await self.session.flush()
        return action

    async def list_action_items(
        self,
        org_id: uuid.UUID,
        meeting_id: Optional[uuid.UUID] = None,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ActionItem]:
        conditions = [ActionItem.organization_id == org_id]
        if meeting_id:
            conditions.append(ActionItem.meeting_id == meeting_id)
        if owner:
            conditions.append(func.lower(ActionItem.owner) == owner.lower())
        if status:
            conditions.append(ActionItem.status == status)

        stmt = select(ActionItem).where(and_(*conditions)).order_by(ActionItem.due_date.nulls_last(), desc(ActionItem.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, org_id: uuid.UUID, action_id: uuid.UUID, update_data: ActionItemUpdate) -> Optional[ActionItem]:
        stmt = select(ActionItem).where(and_(ActionItem.organization_id == org_id, ActionItem.id == action_id))
        result = await self.session.execute(stmt)
        action = result.scalar_one_or_none()
        if not action:
            return None

        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(action, field, value)
            if field == "status" and value == "completed" and not action.completed_at:
                action.completed_at = datetime.now(timezone.utc)

        await self.session.flush()
        return action


class VectorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_meeting_embedding(
        self,
        org_id: uuid.UUID,
        content: str,
        embedding: List[float],
        source_type: str,
        meeting_id: Optional[uuid.UUID] = None,
        memory_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MeetingMemoryEmbedding:
        record = MeetingMemoryEmbedding(
            organization_id=org_id,
            meeting_id=meeting_id,
            memory_id=memory_id,
            source_type=source_type,
            content=content,
            embedding=embedding,
            metadata_=metadata or {},
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def search_meeting_memories(
        self,
        org_id: uuid.UUID,
        query_embedding: List[float],
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        speaker: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        source_type: Optional[str] = None,
        min_similarity: float = 0.0,
        limit: int = 10,
    ) -> List[Tuple[MeetingMemoryEmbedding, float]]:
        """
        Cosine similarity search using pgvector cosine distance operator `<=>`.
        Similarity = 1 - distance.
        """
        # Distance calculation
        distance_expr = MeetingMemoryEmbedding.embedding.cosine_distance(query_embedding).label("distance")

        conditions = [MeetingMemoryEmbedding.organization_id == org_id]
        if meeting_id:
            conditions.append(MeetingMemoryEmbedding.meeting_id == meeting_id)
        if source_type:
            conditions.append(MeetingMemoryEmbedding.source_type == source_type)
        if customer_name:
            conditions.append(MeetingMemoryEmbedding.metadata_["customer_name"].astext.ilike(customer_name))
        if project_name:
            conditions.append(MeetingMemoryEmbedding.metadata_["project_name"].astext.ilike(project_name))
        if speaker:
            conditions.append(MeetingMemoryEmbedding.metadata_["speaker"].astext.ilike(speaker))

        stmt = (
            select(MeetingMemoryEmbedding, distance_expr)
            .where(and_(*conditions))
            .order_by(distance_expr)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        output = []
        for row in rows:
            record, dist = row[0], float(row[1])
            similarity = max(0.0, 1.0 - dist)
            if similarity >= min_similarity:
                output.append((record, similarity))
        return output

    async def search_meeting_memories_keyword(
        self,
        org_id: uuid.UUID,
        query: str,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        speaker: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        source_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Tuple[MeetingMemoryEmbedding, float]]:
        """
        Full-text keyword search using Postgres tsvector/tsquery, ranked by ts_rank.
        Complements vector search for exact terms (names, dates, acronyms) that
        embeddings can under-rank.
        """
        if not query or not query.strip():
            return []

        tsquery = func.plainto_tsquery("english", query)
        tsvector = func.to_tsvector("english", MeetingMemoryEmbedding.content)
        rank_expr = func.ts_rank(tsvector, tsquery).label("rank")

        conditions = [
            MeetingMemoryEmbedding.organization_id == org_id,
            tsvector.op("@@")(tsquery),
        ]
        if meeting_id:
            conditions.append(MeetingMemoryEmbedding.meeting_id == meeting_id)
        if source_type:
            conditions.append(MeetingMemoryEmbedding.source_type == source_type)
        if customer_name:
            conditions.append(MeetingMemoryEmbedding.metadata_["customer_name"].astext.ilike(customer_name))
        if project_name:
            conditions.append(MeetingMemoryEmbedding.metadata_["project_name"].astext.ilike(project_name))
        if speaker:
            conditions.append(MeetingMemoryEmbedding.metadata_["speaker"].astext.ilike(speaker))

        stmt = (
            select(MeetingMemoryEmbedding, rank_expr)
            .where(and_(*conditions))
            .order_by(rank_expr.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]


class WebhookEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_new(self, bot_id: str, event_type: str, payload: Dict[str, Any], idempotency_key: str) -> Tuple[WebhookEvent, bool]:
        """Returns (event, is_created). If already exists, returns (existing_event, False)."""
        stmt = select(WebhookEvent).where(WebhookEvent.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing, False

        event = WebhookEvent(
            bot_id=bot_id,
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
            processed=False,
        )
        self.session.add(event)
        await self.session.flush()
        return event, True

    async def mark_processed(self, event_id: uuid.UUID, error: Optional[str] = None):
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(
                processed=True,
                processing_error=error,
                processed_at=datetime.now(timezone.utc)
            )
        )
        await self.session.execute(stmt)


class ProcessingJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(self, meeting_id: uuid.UUID, job_type: str) -> ProcessingJob:
        job = ProcessingJob(
            meeting_id=meeting_id,
            job_type=job_type,
            status="pending",
            attempts=0,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def start_job(self, job_id: uuid.UUID) -> Optional[ProcessingJob]:
        stmt = select(ProcessingJob).where(ProcessingJob.id == job_id)
        res = await self.session.execute(stmt)
        job = res.scalar_one_or_none()
        if job:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.attempts += 1
            await self.session.flush()
        return job

    async def complete_job(self, job_id: uuid.UUID, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        stmt = select(ProcessingJob).where(ProcessingJob.id == job_id)
        res = await self.session.execute(stmt)
        job = res.scalar_one_or_none()
        if job:
            if error:
                job.status = "failed" if job.attempts >= job.max_attempts else "retrying"
                job.error = error
            else:
                job.status = "completed"
                job.result = result
                job.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
