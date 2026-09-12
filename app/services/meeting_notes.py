"""
Turn a processed meeting into a note in the notebook.

Every meeting the pipeline finishes gets one note, filed under
``Meetings / <year> / <month>`` and tagged with its platform, customer and
project, so the notebook fills itself in an order a person would have chosen
anyway. The note is plain Markdown - the same thing you would write by hand -
with the summary, decisions, commitments, action items and open questions
pulled from what the pipeline extracted.

A note that a person has since edited is left alone on reprocessing: the
generated text is a starting point, not something that overwrites their work.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    ActionItem,
    Meeting,
    Memory,
    MemoryType,
    Note,
    NotebookFolder,
    Participant,
)

ROOT_FOLDER = "Meetings"
MEETING_TAG = "meeting"

#: Section heading per memory type, in the order they appear in the note.
SECTIONS: Sequence[tuple[MemoryType, str]] = (
    (MemoryType.DECISION, "Decisions"),
    (MemoryType.COMMITMENT, "Commitments"),
    (MemoryType.REQUIREMENT, "Requirements"),
    (MemoryType.PROJECT_UPDATE, "Project updates"),
    (MemoryType.CONCERN, "Concerns"),
    (MemoryType.UNRESOLVED_QUESTION, "Open questions"),
    (MemoryType.PREFERENCE, "Preferences"),
    (MemoryType.RELATIONSHIP_CONTEXT, "Relationship context"),
    (MemoryType.FACT, "Facts"),
)

PLATFORM_LABELS = {"google_meet": "Google Meet", "zoom": "Zoom", "teams": "Microsoft Teams"}


def _slug_tag(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = "-".join(part for part in value.strip().lower().replace("_", "-").split())
    return cleaned or None


def meeting_date(meeting: Meeting) -> datetime:
    return meeting.started_at or meeting.created_at or datetime.now(timezone.utc)


def note_title(meeting: Meeting) -> str:
    """``2026-09-12 · Weekly sync`` - sorts chronologically, reads naturally."""
    day = meeting_date(meeting).strftime("%Y-%m-%d")
    return f"{day} · {meeting.title or 'Untitled meeting'}"


def note_tags(meeting: Meeting) -> List[str]:
    tags = [MEETING_TAG]
    for candidate in (
        _slug_tag(PLATFORM_LABELS.get(meeting.platform or "", meeting.platform)),
        _slug_tag(meeting.customer_name),
        _slug_tag(meeting.project_name),
    ):
        if candidate and candidate not in tags:
            tags.append(candidate)
    return tags


def render_note(
    meeting: Meeting,
    participants: Iterable[Participant],
    memories: Iterable[Memory],
    action_items: Iterable[ActionItem],
) -> str:
    """The Markdown body. Sections with nothing in them are omitted."""
    when = meeting_date(meeting)
    lines: List[str] = [f"# {meeting.title or 'Untitled meeting'}", ""]

    meta = [f"**Date:** {when.strftime('%A, %d %B %Y · %H:%M')}"]
    if meeting.platform:
        meta.append(f"**Platform:** {PLATFORM_LABELS.get(meeting.platform, meeting.platform)}")
    if meeting.customer_name:
        meta.append(f"**Customer:** {meeting.customer_name}")
    if meeting.project_name:
        meta.append(f"**Project:** {meeting.project_name}")
    names = sorted({p.name for p in participants if p.name})
    if names:
        meta.append(f"**Participants:** {', '.join(names)}")
    lines.extend(meta)
    lines.append("")

    if meeting.summary:
        lines.extend(["## Summary", "", meeting.summary.strip(), ""])

    actions = list(action_items)
    if actions:
        lines.extend(["## Action items", ""])
        for item in actions:
            box = "x" if item.status == "completed" else " "
            detail = item.task.strip()
            if item.owner:
                detail = f"**{item.owner}** — {detail}"
            extras = []
            if item.due_date:
                extras.append(f"due {item.due_date.isoformat()}")
            if item.priority and item.priority != "medium":
                extras.append(item.priority)
            if extras:
                detail += f" _({', '.join(extras)})_"
            lines.append(f"- [{box}] {detail}")
        lines.append("")

    by_type: Dict[MemoryType, List[Memory]] = {}
    for memory in memories:
        if memory.type == MemoryType.ACTION_ITEM:
            continue  # already listed above from the action_items table
        by_type.setdefault(memory.type, []).append(memory)

    for memory_type, heading in SECTIONS:
        entries = by_type.get(memory_type)
        if not entries:
            continue
        lines.extend([f"## {heading}", ""])
        for memory in sorted(entries, key=lambda m: -(m.importance or 0)):
            text = memory.content.strip()
            if memory.speaker:
                text += f" — _{memory.speaker}_"
            lines.append(f"- {text}")
        lines.append("")

    lines.append(f"---\n_Generated from the meeting record `{meeting.id}`. Edit freely - your changes are kept._")
    return "\n".join(lines).strip() + "\n"


def was_edited_by_user(note: Note) -> bool:
    """A generated note never touches updated_at after creation; a person does."""
    if not note.created_at or not note.updated_at:
        return False
    return note.updated_at - note.created_at > timedelta(seconds=2)


class MeetingNoteService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _folder(self, org_id: uuid.UUID, name: str, parent_id: Optional[uuid.UUID]) -> NotebookFolder:
        stmt = select(NotebookFolder).where(
            NotebookFolder.organization_id == org_id,
            NotebookFolder.parent_id == parent_id,
            NotebookFolder.name == name,
        )
        folder = (await self.session.execute(stmt)).scalars().first()
        if folder is None:
            folder = NotebookFolder(organization_id=org_id, parent_id=parent_id, name=name)
            self.session.add(folder)
            await self.session.flush()
        return folder

    async def folder_for(self, meeting: Meeting) -> NotebookFolder:
        """``Meetings / 2026 / 09 September`` - created on demand."""
        when = meeting_date(meeting)
        root = await self._folder(meeting.organization_id, ROOT_FOLDER, None)
        year = await self._folder(meeting.organization_id, when.strftime("%Y"), root.id)
        return await self._folder(meeting.organization_id, when.strftime("%m %B"), year.id)

    async def sync(self, meeting: Meeting, embed=None) -> Optional[Note]:
        """
        Create or refresh the note for one meeting.

        Returns the note, or None when the meeting has nothing to write yet
        or its note has been edited by hand.
        """
        if not meeting.summary and meeting.processing_status != "completed":
            return None

        existing = (
            await self.session.execute(select(Note).where(Note.meeting_id == meeting.id))
        ).scalars().first()
        if existing is not None and was_edited_by_user(existing):
            return None

        participants = (
            await self.session.execute(select(Participant).where(Participant.meeting_id == meeting.id))
        ).scalars().all()
        memories = (
            await self.session.execute(select(Memory).where(Memory.meeting_id == meeting.id))
        ).scalars().all()
        actions = (
            await self.session.execute(
                select(ActionItem).where(ActionItem.meeting_id == meeting.id).order_by(ActionItem.created_at)
            )
        ).scalars().all()

        title = note_title(meeting)
        content = render_note(meeting, participants, memories, actions)
        folder = await self.folder_for(meeting)
        embedding = await embed(title, content) if embed else None

        if existing is None:
            existing = Note(
                organization_id=meeting.organization_id,
                meeting_id=meeting.id,
                created_by_user_id=meeting.created_by_user_id,
                note_type="meeting",
            )
            self.session.add(existing)

        existing.folder_id = folder.id
        existing.title = title
        existing.content = content
        existing.tags = note_tags(meeting)
        existing.embedding = embedding
        # Keep created/updated equal so the "edited by a person" check stays
        # meaningful after a regeneration.
        stamp = datetime.now(timezone.utc)
        existing.created_at = stamp
        existing.updated_at = stamp
        await self.session.flush()
        return existing

    async def sync_all(self, org_id: uuid.UUID, embed=None) -> Dict[str, int]:
        """Backfill: one note per completed meeting that does not have one yet."""
        stmt = (
            select(Meeting)
            .where(Meeting.organization_id == org_id, Meeting.processing_status == "completed")
            .order_by(Meeting.started_at)
        )
        meetings = (await self.session.execute(stmt)).scalars().all()
        created = skipped = 0
        for meeting in meetings:
            note = await self.sync(meeting, embed=embed)
            if note is None:
                skipped += 1
            else:
                created += 1
        await self.session.commit()
        return {"meetings": len(meetings), "synced": created, "skipped": skipped}
