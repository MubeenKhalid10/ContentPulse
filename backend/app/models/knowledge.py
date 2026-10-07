import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    OrgScoped,
    Timestamps,
    UUIDPk,
    fk_user,
    jsonb_dict,
    jsonb_list,
    str_enum,
)
from app.models.enums import CrawlStatus, KnowledgeJobKind, KnowledgeJobStatus

# Fixed at the schema level: changing the embedding model's dimensionality
# requires a migration and a full re-index.
EMBEDDING_DIMENSIONS = 1536

# Full-text search configuration for keyword retrieval.
TEXT_SEARCH_CONFIG = "english"


class KnowledgeCrawlJob(UUIDPk, CreatedAt, OrgScoped, Base):
    """A website crawl or re-index run, executed in the background (spec rule 6)."""

    __tablename__ = "knowledge_crawl_jobs"
    __table_args__ = (
        Index("ix_knowledge_crawl_jobs_org_created", "organization_id", "created_at"),
    )

    kind: Mapped[KnowledgeJobKind] = mapped_column(
        str_enum(KnowledgeJobKind, "knowledge_job_kind"), nullable=False
    )
    status: Mapped[KnowledgeJobStatus] = mapped_column(
        str_enum(KnowledgeJobStatus, "knowledge_job_status"),
        default=KnowledgeJobStatus.QUEUED,
        server_default=KnowledgeJobStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    root_url: Mapped[str | None] = mapped_column(String(2048))
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_indexed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pages_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    chunks_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Non-fatal problems (e.g. embeddings unavailable) surfaced to the user.
    warnings: Mapped[list[str]] = jsonb_list()
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    requested_by: Mapped[uuid.UUID | None] = fk_user()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Updated while running; a stale heartbeat means the worker died.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeDocument(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("organization_id", "source_url"),)

    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    # Cleaned page text as lightweight markdown ("## Heading" + paragraphs).
    content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    document_type: Mapped[str] = mapped_column(
        String(40), default="web_page", server_default="web_page"
    )
    crawl_status: Mapped[CrawlStatus] = mapped_column(
        str_enum(CrawlStatus, "crawl_status"),
        default=CrawlStatus.PENDING,
        server_default=CrawlStatus.PENDING.value,
        nullable=False,
    )
    crawl_error: Mapped[str | None] = mapped_column(Text)
    # Excluded documents are kept (so re-crawls skip them) but have no chunks.
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_crawl_jobs.id", ondelete="SET NULL")
    )
    # Page metadata preserved for citation: description, canonical, language (spec §9)
    meta: Mapped[dict] = jsonb_dict(name="metadata")
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(UUIDPk, CreatedAt, OrgScoped, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_knowledge_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Section path, e.g. "Services › AI Solutions".
    heading: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            # Section headings (weight A) rank above body text (weight B).
            f"setweight(to_tsvector('{TEXT_SEARCH_CONFIG}', coalesce(heading, '')), 'A') || "
            f"setweight(to_tsvector('{TEXT_SEARCH_CONFIG}', content), 'B')",
            persisted=True,
        ),
    )
    meta: Mapped[dict] = jsonb_dict(name="metadata")
