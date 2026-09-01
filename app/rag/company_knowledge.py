"""
Company Knowledge RAG Engine.
Enables indexing and semantic retrieval over company documents
(PDFs, Markdown guides, Word documents, text files, CSVs).
"""
import uuid
import os
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.embedding import embedding_service
from app.database.repositories import VectorRepository
from app.models.database import CompanyKnowledgeEmbedding
from app.models.schemas import SearchResultItem
from langchain_text_splitters import RecursiveCharacterTextSplitter


class CompanyKnowledgeRAG:
    def __init__(self):
        self.embedding_service = embedding_service
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            length_function=len,
        )

    def chunk_text(self, text: str, source_name: str) -> List[Dict[str, Any]]:
        """Split document text into clean semantic chunks."""
        clean = str(text or "").encode("utf-8", "ignore").decode("utf-8")
        chunks = self.splitter.split_text(clean)
        return [
            {
                "text": c.strip(),
                "source_name": source_name,
                "chunk_index": i,
            }
            for i, c in enumerate(chunks)
            if c.strip()
        ]

    async def index_document(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        document_id: uuid.UUID,
        source_name: str,
        source_type: str,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Chunk and embed a company document into company_knowledge_embeddings.
        """
        chunks = self.chunk_text(text_content, source_name)
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = self.embedding_service.embed_batch(texts)

        for chunk, emb in zip(chunks, embeddings):
            record = CompanyKnowledgeEmbedding(
                organization_id=org_id,
                document_id=document_id,
                source_type=source_type,
                source_name=source_name,
                content=chunk["text"],
                embedding=emb,
                metadata_=metadata or {},
            )
            db.add(record)

        await db.flush()
        return len(chunks)


company_knowledge_rag = CompanyKnowledgeRAG()
