"""
Search backend interface.

Similarity and keyword search are the only two operations where the choice of
database genuinely changes the implementation - everything else is ordinary
SQLAlchemy that works anywhere. Isolating them here is what allows Meet
Companion to run on either a local SQLite file or a Postgres server.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, List, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

#: (record, score) where score is in [0, 1] for vector search and is an
#: unbounded relevance rank for keyword search.
ScoredRow = Tuple[Any, float]


class SearchBackend(ABC):
    name: ClassVar[str]

    def __init__(self, session: AsyncSession):
        self.session = session

    @abstractmethod
    async def vector_search(
        self,
        model: type,
        conditions: Sequence[Any],
        query_embedding: List[float],
        *,
        limit: int,
        min_similarity: float = 0.0,
    ) -> List[ScoredRow]:
        """Rows most similar to `query_embedding`, highest cosine similarity first."""

    @abstractmethod
    async def keyword_search(
        self,
        model: type,
        conditions: Sequence[Any],
        query: str,
        *,
        limit: int,
    ) -> List[ScoredRow]:
        """Rows matching the literal terms in `query`, most relevant first."""


def tokenize(query: str, *, min_length: int = 2) -> List[str]:
    """
    Split a query into distinct lowercase search terms.

    Shared by backends that have no real full-text engine to lean on.
    """
    import re

    seen: List[str] = []
    for token in re.findall(r"[\w']+", query.lower()):
        if len(token) >= min_length and token not in seen:
            seen.append(token)
    return seen
