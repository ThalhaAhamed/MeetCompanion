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

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
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

#: Ties a task line in a note to its action item. HTML comments are invisible
#: in the rendered preview and survive editing the surrounding text.
TASK_MARKER = "<!-- action:{id} -->"
TASK_LINE = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*?)\s*<!-- action:([0-9a-fA-F-]{36}) -->\s*$")

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
            lines.append(f"- [{box}] {detail} {TASK_MARKER.format(id=item.id)}")
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


# ---------------------------------------------------------------------------
# Keeping note checkboxes and action items in step
# ---------------------------------------------------------------------------


def task_states(content: str) -> Dict[uuid.UUID, bool]:
    """action item id -> checked, for every marked task line in a note."""
    states: Dict[uuid.UUID, bool] = {}
    for line in (content or "").splitlines():
        match = TASK_LINE.match(line)
        if match:
            states[uuid.UUID(match.group(4))] = match.group(2).lower() == "x"
    return states


def set_task_state(content: str, action_id: uuid.UUID, checked: bool) -> str:
    """Return the note text with that action item's checkbox set."""
    out = []
    for line in (content or "").splitlines():
        match = TASK_LINE.match(line)
        if match and match.group(4).lower() == str(action_id).lower():
            line = f"{match.group(1)}[{'x' if checked else ' '}]{match.group(3)} {TASK_MARKER.format(id=action_id)}"
        out.append(line)
    text = "\n".join(out)
    return text + ("\n" if (content or "").endswith("\n") else "")


async def apply_note_tasks_to_action_items(session: AsyncSession, note: Note, previous_content: str) -> int:
    """
    A checkbox flipped in the note flips the action item. Only lines whose
    state actually changed are touched, so editing unrelated text never
    resets a task someone completed from the dashboard.
    """
    before = task_states(previous_content)
    after = task_states(note.content)
    changed = {aid: done for aid, done in after.items() if before.get(aid) != done}
    if not changed:
        return 0

    items = (
        await session.execute(
            select(ActionItem).where(
                ActionItem.organization_id == note.organization_id, ActionItem.id.in_(list(changed))
            )
        )
    ).scalars().all()
    for item in items:
        done = changed[item.id]
        item.status = "completed" if done else "open"
        item.completed_at = datetime.now(timezone.utc) if done else None
    await session.flush()
    return len(items)


async def apply_action_item_to_notes(session: AsyncSession, item: ActionItem) -> int:
    """
    An action item completed (or reopened) elsewhere ticks its checkbox in
    the meeting's note. The note's timestamps are preserved so this does not
    count as a person editing it.
    """
    notes = (
        await session.execute(select(Note).where(Note.meeting_id == item.meeting_id))
    ).scalars().all()
    touched = 0
    for note in notes:
        updated = set_task_state(note.content, item.id, item.status == "completed")
        if updated == note.content:
            continue
        stamp = note.updated_at
        note.content = updated
        # Re-assigning the same value is not a change to SQLAlchemy, so the
        # column's onupdate would still fire; flagging it keeps the stamp.
        note.updated_at = stamp
        flag_modified(note, "updated_at")
        touched += 1
    await session.flush()
    return touched


# ---------------------------------------------------------------------------
# Hand-written tasks become action items
# ---------------------------------------------------------------------------

PLAIN_TASK_LINE = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\]\s+(.+?)\s*$")
OWNER_PREFIX = re.compile(r"^\*\*(.+?)\*\*\s*[—:-]\s*(.+)$")


def _task_text(raw: str) -> tuple[Optional[str], str]:
    """'**Sara** — do X' -> ('Sara', 'do X'); anything else -> (None, text)."""
    match = OWNER_PREFIX.match(raw.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, raw.strip()


async def adopt_handwritten_tasks(session: AsyncSession, note: Note) -> Optional[str]:
    """
    Every '- [ ] …' line without a marker becomes an action item, and the
    line gets its marker so the two stay linked from then on.

    Returns the rewritten note text, or None when nothing needed adopting.
    Lines inside fenced code blocks are left alone.
    """
    lines = (note.content or "").split("\n")
    out: List[str] = []
    in_code = False
    changed = False

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        if in_code or TASK_LINE.match(line):
            out.append(line)
            continue
        match = PLAIN_TASK_LINE.match(line)
        if not match:
            out.append(line)
            continue

        owner, task = _task_text(match.group(3))
        if not task:
            out.append(line)
            continue
        done = match.group(2).lower() == "x"
        item = ActionItem(
            organization_id=note.organization_id,
            meeting_id=note.meeting_id,
            note_id=note.id,
            owner=owner,
            task=task,
            status="completed" if done else "open",
            completed_at=datetime.now(timezone.utc) if done else None,
        )
        session.add(item)
        await session.flush()
        out.append(f"{match.group(1)}[{match.group(2)}] {match.group(3).strip()} {TASK_MARKER.format(id=item.id)}")
        changed = True

    if not changed:
        return None
    note.content = "\n".join(out)
    await session.flush()
    return note.content
