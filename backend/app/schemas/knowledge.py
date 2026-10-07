import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import CrawlStatus, KnowledgeJobKind, KnowledgeJobStatus
from app.schemas.common import HttpUrlStr, Name, ORMModel, PatchModel

DocumentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100_000)
]


class CrawlRequest(BaseModel):
    # Defaults to the organization's website.
    url: HttpUrlStr | None = None
    max_pages: Annotated[int, Field(ge=1, le=1000)] | None = None


class JobRead(ORMModel):
    id: uuid.UUID
    kind: KnowledgeJobKind
    status: KnowledgeJobStatus
    root_url: str | None
    max_pages: int
    pages_discovered: int
    pages_crawled: int
    pages_indexed: int
    pages_unchanged: int
    pages_skipped: int
    pages_failed: int
    chunks_created: int
    warnings: list[str]
    error: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobStarted(BaseModel):
    """Spec §37 crawl response, plus the full job for immediate display."""

    job_id: uuid.UUID
    status: KnowledgeJobStatus
    job: JobRead


class KnowledgeSummary(BaseModel):
    website_url: str | None
    documents: int
    indexed_documents: int
    failed_documents: int
    excluded_documents: int
    chunks: int
    embedded_chunks: int
    embeddings_enabled: bool
    embedding_model: str | None
    last_crawled_at: datetime | None
    active_job: JobRead | None
    last_job: JobRead | None


class DocumentListItem(BaseModel):
    id: uuid.UUID
    source_url: str
    title: str | None
    document_type: str
    crawl_status: CrawlStatus
    crawl_error: str | None
    excluded: bool
    word_count: int
    chunk_count: int
    last_crawled_at: datetime | None
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentListItem]
    total: int


class ChunkRead(ORMModel):
    id: uuid.UUID
    chunk_index: int
    heading: str | None
    content: str
    token_count: int | None
    embedded: bool


class DocumentDetail(DocumentListItem):
    content: str | None
    meta: dict
    chunks: list[ChunkRead]


class ManualDocumentCreate(BaseModel):
    title: Name
    content: DocumentText


class DocumentUpdate(PatchModel):
    non_nullable = frozenset({"excluded", "title", "content"})

    excluded: bool | None = None
    # Title/content edits are only allowed on manually added documents.
    title: Name | None = None
    content: DocumentText | None = None


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    limit: Annotated[int, Field(ge=1, le=20)] = 8


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    url: str
    document_type: str
    heading: str | None
    snippet: str
    score: float
    match: Literal["keyword", "semantic", "both"]


class SearchResponse(BaseModel):
    mode: Literal["hybrid", "keyword"]
    results: list[SearchResult]
