"""
Postgres search backend.

Uses pgvector for similarity and Postgres full-text search for keywords, both
executed in the database. This is the backend to use for shared or large
deployments.
"""
from __future__ import annotations

from typing import Any, List, Sequence

from sqlalchemy import and_, func, select, text

from app.providers.database.base import ScoredRow, SearchBackend

# The ivfflat index defaults to probes=1, scanning roughly 1% of the index's
# clusters per query. At realistic per-workspace data volumes that skips true
# nearest neighbours outright rather than merely ranking them lower, so recall
# suffers badly. Raising probes trades a little query time for dramatically
# better recall.
IVFFLAT_PROBES = 10


class PostgresSearchBackend(SearchBackend):
    name = "postgresql"

    async def vector_search(
        self,
        model: type,
        conditions: Sequence[Any],
        query_embedding: List[float],
        *,
        limit: int,
        min_similarity: float = 0.0,
    ) -> List[ScoredRow]:
        await self.session.execute(text(f"SET LOCAL ivfflat.probes = {IVFFLAT_PROBES}"))

        distance = model.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(model, distance)
            .where(and_(*conditions))
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        results: List[ScoredRow] = []
        for record, dist in rows:
            similarity = max(0.0, 1.0 - float(dist))
            if similarity >= min_similarity:
                results.append((record, similarity))
        return results

    async def keyword_search(
        self,
        model: type,
        conditions: Sequence[Any],
        query: str,
        *,
        limit: int,
    ) -> List[ScoredRow]:
        if not query.strip():
            return []

        tsquery = func.plainto_tsquery("english", query)
        tsvector = func.to_tsvector("english", model.content)
        rank = func.ts_rank(tsvector, tsquery).label("rank")

        stmt = (
            select(model, rank)
            .where(and_(*conditions, tsvector.op("@@")(tsquery)))
            .order_by(rank.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(record, float(score)) for record, score in rows]
