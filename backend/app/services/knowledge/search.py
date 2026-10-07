"""Knowledge retrieval (spec §17): hybrid keyword + semantic search.

Keyword search (Postgres full-text) always works. When an embedding provider
is configured, vector search runs too and the two rankings are fused with
Reciprocal Rank Fusion, so exact terms (product names) and paraphrases
("help companies automate work") both find the right chunks.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingError, EmbeddingProvider, gate
from app.core.logging import logger
from app.models.knowledge import TEXT_SEARCH_CONFIG, KnowledgeChunk, KnowledgeDocument

CANDIDATES = 30
RRF_K = 60
HIGHLIGHT_START = "⟦"  # ⟦
HIGHLIGHT_END = "⟧"  # ⟧

Match = Literal["keyword", "semantic", "both"]


@dataclass
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    url: str
    document_type: str
    heading: str | None
    content: str
    snippet: str
    score: float
    match: Match


def _keyword_query(query: str):
    """OR the query's lexemes: natural questions shouldn't need every word to match."""
    plain = func.plainto_tsquery(TEXT_SEARCH_CONFIG, query)
    return func.to_tsquery(TEXT_SEARCH_CONFIG, func.replace(cast(plain, Text), "&", "|"))


async def _keyword_ids(db: AsyncSession, organization_id: uuid.UUID, query: str) -> list[uuid.UUID]:
    tsquery = _keyword_query(query)
    # Chunks containing every query term outrank ones that repeat a single term.
    matches_all = KnowledgeChunk.search_vector.op("@@")(
        func.plainto_tsquery(TEXT_SEARCH_CONFIG, query)
    )
    rank = func.ts_rank(KnowledgeChunk.search_vector, tsquery)
    rows = await db.scalars(
        select(KnowledgeChunk.id)
        .where(
            KnowledgeChunk.organization_id == organization_id,
            KnowledgeChunk.search_vector.op("@@")(tsquery),
        )
        .order_by(matches_all.desc(), rank.desc())
        .limit(CANDIDATES)
    )
    return list(rows)


async def _semantic_ids(
    db: AsyncSession, organization_id: uuid.UUID, vector: list[float], min_similarity: float
) -> list[uuid.UUID]:
    # The HNSW index is shared by all tenants. Iterative scans keep searching
    # until enough rows pass the organization filter (pgvector >= 0.8).
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    rows = await db.execute(
        select(KnowledgeChunk.id, distance.label("distance"))
        .where(
            KnowledgeChunk.organization_id == organization_id,
            KnowledgeChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(CANDIDATES)
    )
    # Nearest neighbours always exist; drop ones that aren't actually related.
    # relaxed_order may return slightly out-of-order rows; re-sort exactly.
    max_distance = 1 - min_similarity
    return [r.id for r in sorted(rows, key=lambda r: r.distance) if r.distance <= max_distance]


def _fuse(*rankings: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


async def search_knowledge(
    db: AsyncSession,
    organization_id: uuid.UUID,
    query: str,
    *,
    limit: int = 8,
    provider: EmbeddingProvider | None = None,
    min_similarity: float = 0.2,
) -> tuple[list[SearchHit], bool]:
    """Return (hits, semantic_used). Always scoped to one organization."""
    keyword = await _keyword_ids(db, organization_id, query)

    semantic: list[uuid.UUID] = []
    semantic_used = False
    if provider is not None:
        try:
            [vector] = await gate(provider).embed(
                [query],
                organization_id=organization_id,
                workflow="knowledge_search",
                interactive=True,
            )
        except EmbeddingError as exc:
            logger.warning("Query embedding failed, falling back to keyword search: %s", exc)
        else:
            semantic = await _semantic_ids(db, organization_id, vector, min_similarity)
            semantic_used = True

    scores = _fuse(keyword, semantic)
    top = sorted(scores, key=scores.__getitem__, reverse=True)[:limit]
    if not top:
        return [], semantic_used

    headline = func.ts_headline(
        TEXT_SEARCH_CONFIG,
        KnowledgeChunk.content,
        _keyword_query(query),
        f"StartSel={HIGHLIGHT_START}, StopSel={HIGHLIGHT_END}, MaxWords=40, MinWords=18, "
        'MaxFragments=2, FragmentDelimiter=" … "',
    )
    rows = await db.execute(
        select(KnowledgeChunk, KnowledgeDocument, headline.label("snippet"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.id.in_(top), KnowledgeChunk.organization_id == organization_id)
    )
    by_id = {chunk.id: (chunk, doc, snippet) for chunk, doc, snippet in rows}

    keyword_set, semantic_set = set(keyword), set(semantic)
    hits: list[SearchHit] = []
    for chunk_id in top:
        if chunk_id not in by_id:
            continue
        chunk, doc, snippet = by_id[chunk_id]
        in_kw, in_sem = chunk_id in keyword_set, chunk_id in semantic_set
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=doc.id,
                title=doc.title,
                url=doc.source_url,
                document_type=doc.document_type,
                heading=chunk.heading,
                content=chunk.content,
                # Semantic-only hits may share no words with the query.
                snippet=snippet if in_kw else chunk.content[:280],
                score=round(scores[chunk_id], 5),
                match="both" if in_kw and in_sem else ("keyword" if in_kw else "semantic"),
            )
        )
    return hits, semantic_used
