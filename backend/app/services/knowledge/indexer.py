"""Chunk + embed documents into knowledge_chunks."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingError, EmbeddingProvider, embedding_input, gate
from app.models.enums import CrawlStatus
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge.chunker import chunk_markdown


@dataclass
class IndexResult:
    chunks: int
    embedded: bool
    # Set when embedding failed; the document stays keyword-searchable.
    embedding_error: EmbeddingError | None = None


def content_hash(title: str | None, markdown: str) -> str:
    return hashlib.sha256(f"{title or ''}\n{markdown}".encode()).hexdigest()


async def clear_chunks(db: AsyncSession, document: KnowledgeDocument) -> None:
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))


async def _existing_vectors(
    db: AsyncSession, document: KnowledgeDocument, provider: EmbeddingProvider
) -> dict[str, list[float]]:
    """Embedding input -> vector for the document's current chunks embedded
    by `provider`'s model."""
    rows = await db.execute(
        select(
            KnowledgeChunk.heading,
            KnowledgeChunk.content,
            KnowledgeChunk.meta,
            KnowledgeChunk.embedding,
        ).where(
            KnowledgeChunk.document_id == document.id,
            KnowledgeChunk.embedding_model == provider.model,
            KnowledgeChunk.embedding.is_not(None),
        )
    )
    return {
        embedding_input((r.meta or {}).get("title"), r.heading, r.content): list(r.embedding)
        for r in rows
    }


async def index_document(
    db: AsyncSession,
    document: KnowledgeDocument,
    provider: EmbeddingProvider | None,
) -> IndexResult:
    """Replace the document's chunks. Caller commits.

    Chunks whose text (page title, heading, content) is unchanged keep their
    vector from the same embedding model: re-indexing an unchanged document
    makes no embedding request."""
    reusable = await _existing_vectors(db, document, provider) if provider else {}
    await clear_chunks(db, document)
    pieces = chunk_markdown(document.content or "")

    vectors: list[list[float]] | None = None
    error: EmbeddingError | None = None
    if provider and pieces:
        texts = [embedding_input(document.title, p.heading, p.content) for p in pieces]
        missing = [t for t in dict.fromkeys(texts) if t not in reusable]
        try:
            if missing:
                fresh = await gate(provider).embed(
                    missing,
                    organization_id=document.organization_id,
                    workflow="knowledge_embedding",
                )
                reusable.update(zip(missing, fresh, strict=True))
            vectors = [reusable[t] for t in texts]
        except EmbeddingError as exc:
            error = exc

    for i, piece in enumerate(pieces):
        db.add(
            KnowledgeChunk(
                organization_id=document.organization_id,
                document_id=document.id,
                chunk_index=piece.index,
                heading=piece.heading,
                content=piece.content,
                token_count=piece.token_estimate,
                embedding=vectors[i] if vectors else None,
                embedding_model=provider.model if vectors and provider else None,
                meta={"url": document.source_url, "title": document.title},
            )
        )

    document.crawl_status = CrawlStatus.EMBEDDED if vectors else CrawlStatus.EXTRACTED
    document.crawl_error = f"Embedding failed: {error}" if error else None
    return IndexResult(chunks=len(pieces), embedded=vectors is not None, embedding_error=error)
