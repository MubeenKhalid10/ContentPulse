"""Chunk + embed documents into knowledge_chunks."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete
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


async def index_document(
    db: AsyncSession,
    document: KnowledgeDocument,
    provider: EmbeddingProvider | None,
) -> IndexResult:
    """Replace the document's chunks. Caller commits."""
    await clear_chunks(db, document)
    pieces = chunk_markdown(document.content or "")

    vectors: list[list[float]] | None = None
    error: EmbeddingError | None = None
    if provider and pieces:
        try:
            vectors = await gate(provider).embed(
                [embedding_input(document.title, p.heading, p.content) for p in pieces],
                organization_id=document.organization_id,
                workflow="knowledge_embedding",
            )
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
