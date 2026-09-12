"""
Notebook endpoints: folders, notes, filtering and Ask AI.

Ask AI runs through the configured LLM provider and is grounded in a retrieval
step, so only relevant notes reach the model rather than the entire notebook.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_org_id, get_current_user
from app.database.connection import get_db
from app.database.notebook_repository import (
    NoteRepository,
    NotebookFolderRepository,
    build_folder_tree,
)
from app.models.database import Note, User
from app.providers.database import get_search_backend
from app.providers.llm import ChatMessage, LLMConfigError, LLMError
from app.services.embedding import embedding_service
from app.services.llm import get_llm_provider

router = APIRouter(prefix="/api/notebook", tags=["notebook"])

#: How many notes are handed to the model for one question. Enough for a
#: grounded answer without blowing a small local model's context window.
ASK_CONTEXT_NOTES = 8
#: Characters of each note included in that context.
ASK_NOTE_EXCERPT = 2000

ASK_SYSTEM_PROMPT = """You are a research assistant answering questions about the user's own notes.

Rules:
- Answer only from the provided notes. Never invent details.
- If the notes do not contain the answer, say so plainly.
- Cite the notes you used by their title.
- Be concise and specific."""


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[uuid.UUID] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_id: Optional[uuid.UUID] = None
    clear_parent: bool = False


class NoteCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=500)
    content: str = ""
    folder_id: Optional[uuid.UUID] = None
    meeting_id: Optional[uuid.UUID] = None
    note_type: str = "note"
    tags: List[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    note_type: Optional[str] = None
    tags: Optional[List[str]] = None
    is_favorite: Optional[bool] = None
    folder_id: Optional[uuid.UUID] = None
    move_to_root: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    note_ids: Optional[List[uuid.UUID]] = None
    folder_id: Optional[uuid.UUID] = None
    favorites_only: bool = False


def _serialize_note(note: Note, *, include_content: bool = True) -> Dict[str, Any]:
    data = {
        "id": str(note.id),
        "title": note.title,
        "note_type": note.note_type,
        "tags": note.tags or [],
        "is_favorite": note.is_favorite,
        "folder_id": str(note.folder_id) if note.folder_id else None,
        "meeting_id": str(note.meeting_id) if note.meeting_id else None,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
    if include_content:
        data["content"] = note.content
    else:
        data["excerpt"] = (note.content or "")[:240]
    return data


async def _embed_note(title: str, content: str) -> Optional[List[float]]:
    """
    Embed a note for Ask AI retrieval.

    Failure is non-fatal: the note still saves and stays findable by text
    search, it simply will not surface through semantic retrieval.
    """
    text = f"{title}\n\n{content}".strip()
    if not text:
        return None
    try:
        return await embedding_service.embed_text_async(text)
    except Exception as exc:
        print(f"[WARN] Could not embed note: {exc}")
        return None


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.get("/folders")
async def list_folders(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    folders = await NotebookFolderRepository(db).list_all(org_id)

    counts_by_folder = {
        folder_id: int(count)
        for folder_id, count in (
            await db.execute(
                select(Note.folder_id, func.count())
                .where(Note.organization_id == org_id)
                .group_by(Note.folder_id)
            )
        ).all()
    }

    return {
        "folders": build_folder_tree(folders, counts_by_folder),
        "counts": await NoteRepository(db).counts(org_id),
    }


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NotebookFolderRepository(db)
    if body.parent_id and not await repo.get(org_id, body.parent_id):
        raise HTTPException(status_code=404, detail="Parent folder not found.")

    folder = await repo.create(org_id, body.name, body.parent_id)
    return {"id": str(folder.id), "name": folder.name,
            "parent_id": str(folder.parent_id) if folder.parent_id else None}


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: uuid.UUID,
    body: FolderUpdate,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NotebookFolderRepository(db)
    folder = await repo.get(org_id, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found.")

    if body.name:
        folder = await repo.rename(folder, body.name)

    if body.clear_parent:
        folder = await repo.move(folder, None)
    elif body.parent_id is not None:
        if not await repo.get(org_id, body.parent_id):
            raise HTTPException(status_code=404, detail="Parent folder not found.")
        if await repo.would_create_cycle(org_id, folder_id, body.parent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A folder cannot be moved inside itself.",
            )
        folder = await repo.move(folder, body.parent_id)

    return {"id": str(folder.id), "name": folder.name,
            "parent_id": str(folder.parent_id) if folder.parent_id else None}


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: uuid.UUID,
    cascade: bool = Query(False, description="Also delete the folder's notes and subfolders."),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NotebookFolderRepository(db)
    folder = await repo.get(org_id, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found.")

    await repo.delete(folder, cascade=cascade)
    return {"deleted": str(folder_id), "cascade": cascade}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@router.get("/notes")
async def list_notes(
    q: Optional[str] = None,
    folder_id: Optional[uuid.UUID] = None,
    unfiled: bool = False,
    meeting_id: Optional[uuid.UUID] = None,
    note_type: Optional[str] = None,
    tag: Optional[str] = None,
    favorites_only: bool = False,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    sort: str = Query("updated", pattern="^(updated|created|title)$"),
    descending: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NoteRepository(db)
    conditions = repo.build_filters(
        org_id,
        folder_id=folder_id,
        unfiled=unfiled,
        meeting_id=meeting_id,
        note_type=note_type,
        tag=tag,
        favorites_only=favorites_only,
        since=since,
        until=until,
    )
    notes, total = await repo.list(
        conditions, query=q, sort=sort, descending=descending, limit=limit, offset=offset
    )
    return {
        "notes": [_serialize_note(n, include_content=False) for n in notes],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/tags")
async def list_tags(
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return {"tags": await NoteRepository(db).list_tags(org_id)}


@router.post("/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if body.folder_id and not await NotebookFolderRepository(db).get(org_id, body.folder_id):
        raise HTTPException(status_code=404, detail="Folder not found.")

    note = await NoteRepository(db).create(
        org_id,
        title=body.title or "Untitled",
        content=body.content,
        folder_id=body.folder_id,
        meeting_id=body.meeting_id,
        note_type=body.note_type,
        tags=body.tags,
        created_by_user_id=user.id,
        embedding=await _embed_note(body.title, body.content),
    )
    return _serialize_note(note)


@router.get("/notes/{note_id}")
async def get_note(
    note_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    note = await NoteRepository(db).get(org_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    return _serialize_note(note)


@router.patch("/notes/{note_id}")
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NoteRepository(db)
    note = await repo.get(org_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")

    if body.folder_id and not await NotebookFolderRepository(db).get(org_id, body.folder_id):
        raise HTTPException(status_code=404, detail="Folder not found.")

    fields: Dict[str, Any] = {
        "title": body.title,
        "content": body.content,
        "note_type": body.note_type,
        "tags": body.tags,
        "is_favorite": body.is_favorite,
        "folder_id": body.folder_id,
    }

    # Re-embed only when the text actually changed, so toggling a favourite
    # does not pay for an embedding pass.
    if body.title is not None or body.content is not None:
        fields["embedding"] = await _embed_note(
            body.title if body.title is not None else note.title,
            body.content if body.content is not None else note.content,
        )

    note = await repo.update(note, **fields)

    if body.move_to_root:
        note.folder_id = None
        await db.commit()
        await db.refresh(note)

    return _serialize_note(note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    repo = NoteRepository(db)
    note = await repo.get(org_id, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")

    await repo.delete(note)
    return {"deleted": str(note_id)}


# ---------------------------------------------------------------------------
# Ask AI
# ---------------------------------------------------------------------------


@router.post("/ask")
async def ask_notebook(
    body: AskRequest,
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Answer a question about the user's notes.

    An explicit note selection is used verbatim; otherwise the question is
    embedded and the most relevant notes in scope are retrieved, so a large
    notebook never has to fit in the model's context.
    """
    try:
        provider = get_llm_provider()
    except LLMConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{exc} Configure a provider in Settings before using Ask AI.",
        )

    repo = NoteRepository(db)
    conditions = repo.build_filters(
        org_id,
        folder_id=body.folder_id,
        favorites_only=body.favorites_only,
        note_ids=body.note_ids,
    )

    if body.note_ids:
        notes, _ = await repo.list(conditions, limit=ASK_CONTEXT_NOTES)
    else:
        notes = await _retrieve_relevant_notes(db, conditions, body.question)

    if not notes:
        return {
            "answer": "There are no notes in scope to answer from yet.",
            "sources": [],
            "provider": provider.name,
        }

    context = "\n\n".join(
        f"### {note.title}\n{(note.content or '')[:ASK_NOTE_EXCERPT]}" for note in notes
    )
    messages = [
        ChatMessage(role="system", content=ASK_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=f"Notes:\n\n{context}\n\n---\n\nQuestion: {body.question.strip()}",
        ),
    ]

    try:
        answer = await provider.complete(messages)
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "answer": answer,
        "sources": [{"id": str(n.id), "title": n.title} for n in notes],
        "provider": provider.name,
        "model": provider.config.model,
    }


async def _retrieve_relevant_notes(
    db: AsyncSession, conditions: List[Any], question: str
) -> List[Note]:
    """
    Pick the notes most likely to answer the question.

    Semantic retrieval first; literal keyword matching fills the remainder so
    exact terms (names, dates, acronyms) that embeddings under-rank still make
    it into context.
    """
    backend = get_search_backend(db)
    selected: List[Note] = []
    seen: set = set()

    try:
        embedded = await embedding_service.embed_text_async(question)
        embeddable = list(conditions) + [Note.embedding.isnot(None)]
        for note, _score in await backend.vector_search(
            Note, embeddable, embedded, limit=ASK_CONTEXT_NOTES
        ):
            if note.id not in seen:
                seen.add(note.id)
                selected.append(note)
    except Exception as exc:
        print(f"[WARN] Semantic note retrieval unavailable: {exc}")

    if len(selected) < ASK_CONTEXT_NOTES:
        for note, _score in await backend.keyword_search(
            Note, conditions, question, limit=ASK_CONTEXT_NOTES
        ):
            if note.id not in seen:
                seen.add(note.id)
                selected.append(note)
            if len(selected) >= ASK_CONTEXT_NOTES:
                break

    return selected[:ASK_CONTEXT_NOTES]
