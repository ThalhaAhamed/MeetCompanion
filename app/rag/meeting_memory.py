"""
Meeting Memory RAG Engine.
Indexes meeting transcripts and structured memories into vector store,
and provides semantic search with customer, project, and speaker filtering.
"""
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.embedding import embedding_service
from app.rag.chunking import transcript_chunker
from app.database.repositories import VectorRepository, MeetingRepository, MemoryRepository
from app.models.schemas import SearchMeetingMemoryQuery, SearchResultItem, SearchMeetingMemoryResponse
from app.models.database import MemoryType, Meeting, Memory
from app.rag.retrieval import reciprocal_rank_fusion


class MeetingMemoryRAG:
    def __init__(self):
        self.embedding_service = embedding_service
        self.chunker = transcript_chunker

    async def index_meeting(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        meeting_id: uuid.UUID,
        transcript_segments: List[Dict[str, Any]],
        memories: List[Memory],
        meeting_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Dual-source indexer:
        1. Chunks raw transcript utterances and embeds them.
        2. Embeds all structured memories with rich metadata tags.
        """
        vector_repo = VectorRepository(db)
        indexed_count = 0
        meta = meeting_metadata or {}
        customer_name = meta.get("customer_name")
        project_name = meta.get("project_name")
        meeting_title = meta.get("title")

        # 1. Index Transcript Chunks
        chunks = self.chunker.chunk_transcript_segments(transcript_segments)
        if chunks:
            chunk_texts = [c.text for c in chunks]
            embeddings = await self.embedding_service.embed_batch_async(chunk_texts)

            for chunk, emb in zip(chunks, embeddings):
                chunk_meta = {
                    "customer_name": customer_name,
                    "project_name": project_name,
                    "title": meeting_title,
                    "speaker": chunk.speaker,
                    "start_time": chunk.start_time,
                    "end_time": chunk.end_time,
                    "segment_indices": chunk.segment_indices,
                    "source": "transcript_chunk",
                }
                await vector_repo.add_meeting_embedding(
                    org_id=org_id,
                    content=chunk.text,
                    embedding=emb,
                    source_type="transcript_chunk",
                    meeting_id=meeting_id,
                    metadata=chunk_meta,
                )
                indexed_count += 1

        # 2. Index Structured Memories
        if memories:
            memory_texts = [
                f"[{m.type.value.upper()}] (Speaker: {m.speaker or 'Unknown'}): {m.content}"
                for m in memories
            ]
            mem_embeddings = await self.embedding_service.embed_batch_async(memory_texts)

            for mem, emb in zip(memories, mem_embeddings):
                mem_meta = {
                    "customer_name": mem.customer_name or customer_name,
                    "project_name": mem.project_name or project_name,
                    "title": meeting_title,
                    "speaker": mem.speaker,
                    "memory_type": mem.type.value,
                    "importance": mem.importance,
                    "source": "memory",
                }
                await vector_repo.add_meeting_embedding(
                    org_id=org_id,
                    content=mem.content,
                    embedding=emb,
                    source_type="memory",
                    meeting_id=meeting_id,
                    memory_id=mem.id,
                    metadata=mem_meta,
                )
                indexed_count += 1

        await db.flush()
        return indexed_count

    async def index_memory(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        meeting_id: uuid.UUID,
        memory: Memory,
        meeting_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Embed and index a single structured memory added outside the normal
        post-call pipeline (e.g. via an MCP write tool during a live meeting).
        """
        vector_repo = VectorRepository(db)
        meta = meeting_metadata or {}
        text_repr = f"[{memory.type.value.upper()}] (Speaker: {memory.speaker or 'Unknown'}): {memory.content}"
        embedding = await self.embedding_service.embed_text_async(text_repr)
        mem_meta = {
            "customer_name": memory.customer_name or meta.get("customer_name"),
            "project_name": memory.project_name or meta.get("project_name"),
            "title": meta.get("title"),
            "speaker": memory.speaker,
            "memory_type": memory.type.value,
            "importance": memory.importance,
            "source": "memory",
        }
        await vector_repo.add_meeting_embedding(
            org_id=org_id,
            content=memory.content,
            embedding=embedding,
            source_type="memory",
            meeting_id=meeting_id,
            memory_id=memory.id,
            metadata=mem_meta,
        )
        await db.flush()

    async def search(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        query: str,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
        speaker: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        source_type: Optional[str] = None,
        min_similarity: float = 0.0,
        limit: int = 10,
    ) -> List[SearchResultItem]:
        """
        Hybrid search across indexed meeting transcripts and structured memories:
        combines semantic vector similarity with Postgres full-text keyword search,
        fused via Reciprocal Rank Fusion so exact terms (names, dates, acronyms)
        aren't lost to embedding-only ranking.
        """
        query_embedding = await self.embedding_service.embed_text_async(query)
        vector_repo = VectorRepository(db)
        candidate_pool = max(limit * 3, 20)

        vector_results = await vector_repo.search_meeting_memories(
            org_id=org_id,
            query_embedding=query_embedding,
            customer_name=customer_name,
            project_name=project_name,
            speaker=speaker,
            meeting_id=meeting_id,
            source_type=source_type,
            min_similarity=min_similarity,
            limit=candidate_pool,
        )
        keyword_results = await vector_repo.search_meeting_memories_keyword(
            org_id=org_id,
            query=query,
            customer_name=customer_name,
            project_name=project_name,
            speaker=speaker,
            meeting_id=meeting_id,
            source_type=source_type,
            limit=candidate_pool,
        )

        similarity_by_id: Dict[str, float] = {}
        records_by_id: Dict[str, Any] = {}
        vector_ranked = []
        for record, similarity in vector_results:
            rid = str(record.id)
            similarity_by_id[rid] = similarity
            records_by_id[rid] = record
            vector_ranked.append({"id": rid})

        keyword_ranked = []
        for record, _rank in keyword_results:
            rid = str(record.id)
            records_by_id.setdefault(rid, record)
            keyword_ranked.append({"id": rid})

        fused = reciprocal_rank_fusion([vector_ranked, keyword_ranked], key_field="id")

        results: List[SearchResultItem] = []
        for item in fused[:limit]:
            record = records_by_id[item["id"]]
            meta = record.metadata_ or {}
            results.append(
                SearchResultItem(
                    id=record.id,
                    content=record.content,
                    similarity=round(similarity_by_id.get(item["id"], 0.0), 4),
                    source_type=record.source_type,
                    meeting_id=record.meeting_id,
                    memory_id=record.memory_id,
                    meeting_title=meta.get("title"),
                    meeting_date=str(record.created_at.date()) if record.created_at else None,
                    customer_name=meta.get("customer_name"),
                    project_name=meta.get("project_name"),
                    speaker=meta.get("speaker"),
                    memory_type=meta.get("memory_type"),
                    metadata=meta,
                )
            )

        return results


meeting_memory_rag = MeetingMemoryRAG()
