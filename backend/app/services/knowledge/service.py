"""Knowledge base operations used by the API (spec §37)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embedding_provider
from app.core.config import Settings
from app.core.errors import AppError, Conflict, ErrorCode, NotFound
from app.models.enums import CrawlStatus, KnowledgeJobKind, KnowledgeJobStatus
from app.models.knowledge import KnowledgeChunk, KnowledgeCrawlJob, KnowledgeDocument
from app.models.organization import Organization
from app.schemas.knowledge import (
    ChunkRead,
    DocumentDetail,
    DocumentListItem,
    DocumentPage,
    DocumentUpdate,
    JobRead,
    KnowledgeSummary,
    ManualDocumentCreate,
)
from app.services import audit
from app.services.audit import AuditAction
from app.services.knowledge.indexer import clear_chunks, content_hash, index_document
from app.workers import knowledge_tasks
from app.workers.tasks import enqueue

ACTIVE = (KnowledgeJobStatus.QUEUED, KnowledgeJobStatus.RUNNING)


async def _active_job(db: AsyncSession, organization_id: uuid.UUID) -> KnowledgeCrawlJob | None:
    return await db.scalar(
        select(KnowledgeCrawlJob)
        .where(
            KnowledgeCrawlJob.organization_id == organization_id,
            KnowledgeCrawlJob.status.in_(ACTIVE),
        )
        .order_by(KnowledgeCrawlJob.created_at.desc())
        .with_for_update()
    )


async def _ensure_no_active_job(db: AsyncSession, organization_id: uuid.UUID) -> None:
    active = await _active_job(db, organization_id)
    if active is None:
        return
    is_stale = await db.scalar(
        select(func.count())
        .select_from(KnowledgeCrawlJob)
        .where(KnowledgeCrawlJob.id == active.id, knowledge_tasks.stale_condition())
    )
    if is_stale:
        active.status = KnowledgeJobStatus.FAILED
        active.error = "Interrupted: the worker stopped responding."
        active.finished_at = datetime.now(UTC)
        return
    raise AppError(
        ErrorCode.CONFLICT,
        "A crawl or re-index is already running for this organization.",
        details={"job_id": str(active.id)},
    )


async def start_crawl(
    db: AsyncSession,
    *,
    organization: Organization,
    user_id: uuid.UUID,
    url: str | None,
    max_pages: int | None,
    settings: Settings,
) -> KnowledgeCrawlJob:
    root_url = url or organization.website_url
    if not root_url:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Add your website to the organization profile, or provide a URL to crawl.",
        )
    pages = min(max_pages or settings.crawler_default_max_pages, settings.crawler_max_pages_limit)

    await _ensure_no_active_job(db, organization.id)
    job = KnowledgeCrawlJob(
        organization_id=organization.id,
        kind=KnowledgeJobKind.CRAWL,
        root_url=root_url,
        max_pages=pages,
        requested_by=user_id,
    )
    db.add(job)
    await db.flush()
    audit.record(
        db,
        organization_id=organization.id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_CRAWL_STARTED,
        entity_type="knowledge_crawl_job",
        entity_id=job.id,
        new_value={"url": root_url, "max_pages": pages},
    )
    await db.commit()
    enqueue("knowledge.crawl", job.id)
    return job


async def start_reindex(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> KnowledgeCrawlJob:
    await _ensure_no_active_job(db, organization_id)
    job = KnowledgeCrawlJob(
        organization_id=organization_id,
        kind=KnowledgeJobKind.REINDEX,
        max_pages=0,
        requested_by=user_id,
    )
    db.add(job)
    await db.flush()
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_REINDEX_STARTED,
        entity_type="knowledge_crawl_job",
        entity_id=job.id,
    )
    await db.commit()
    enqueue("knowledge.reindex", job.id)
    return job


async def get_job(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID
) -> KnowledgeCrawlJob:
    job = await db.scalar(
        select(KnowledgeCrawlJob).where(
            KnowledgeCrawlJob.id == job_id, KnowledgeCrawlJob.organization_id == organization_id
        )
    )
    if job is None:
        raise NotFound("Job")
    return job


async def list_jobs(
    db: AsyncSession, organization_id: uuid.UUID, limit: int
) -> list[KnowledgeCrawlJob]:
    rows = await db.scalars(
        select(KnowledgeCrawlJob)
        .where(KnowledgeCrawlJob.organization_id == organization_id)
        .order_by(KnowledgeCrawlJob.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def cancel_job(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, user_id: uuid.UUID
) -> KnowledgeCrawlJob:
    job = await get_job(db, organization_id, job_id)
    if job.status not in ACTIVE:
        raise Conflict("This job has already finished.")
    job.cancel_requested = True
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_CRAWL_CANCELLED,
        entity_type="knowledge_crawl_job",
        entity_id=job.id,
    )
    await db.commit()
    await db.refresh(job)
    return job


async def summary(
    db: AsyncSession, organization: Organization, settings: Settings
) -> KnowledgeSummary:
    org_id = organization.id
    doc_counts = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(
                    KnowledgeDocument.crawl_status.in_(
                        [CrawlStatus.EXTRACTED, CrawlStatus.EMBEDDED]
                    ),
                    KnowledgeDocument.excluded.is_(False),
                ),
                func.count().filter(KnowledgeDocument.crawl_status == CrawlStatus.FAILED),
                func.count().filter(KnowledgeDocument.excluded.is_(True)),
                func.max(KnowledgeDocument.last_crawled_at),
            ).where(KnowledgeDocument.organization_id == org_id)
        )
    ).one()
    chunk_counts = (
        await db.execute(
            select(func.count(), func.count(KnowledgeChunk.embedding)).where(
                KnowledgeChunk.organization_id == org_id
            )
        )
    ).one()
    jobs = await list_jobs(db, org_id, 2)
    active = next((j for j in jobs if j.status in ACTIVE), None)
    last = next((j for j in jobs if j.status not in ACTIVE), None)
    provider = get_embedding_provider(settings)
    return KnowledgeSummary(
        website_url=organization.website_url,
        documents=doc_counts[0],
        indexed_documents=doc_counts[1],
        failed_documents=doc_counts[2],
        excluded_documents=doc_counts[3],
        last_crawled_at=doc_counts[4],
        chunks=chunk_counts[0],
        embedded_chunks=chunk_counts[1],
        embeddings_enabled=provider is not None,
        embedding_model=provider.model if provider else None,
        active_job=JobRead.model_validate(active) if active else None,
        last_job=JobRead.model_validate(last) if last else None,
    )


def _chunk_count():
    return (
        select(func.count())
        .where(KnowledgeChunk.document_id == KnowledgeDocument.id)
        .correlate(KnowledgeDocument)
        .scalar_subquery()
    )


def _list_item(doc: KnowledgeDocument, chunks: int) -> DocumentListItem:
    return DocumentListItem(
        id=doc.id,
        source_url=doc.source_url,
        title=doc.title,
        document_type=doc.document_type,
        crawl_status=doc.crawl_status,
        crawl_error=doc.crawl_error,
        excluded=doc.excluded,
        word_count=doc.word_count,
        chunk_count=chunks,
        last_crawled_at=doc.last_crawled_at,
        updated_at=doc.updated_at,
    )


async def list_documents(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    q: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> DocumentPage:
    filters = [KnowledgeDocument.organization_id == organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(KnowledgeDocument.title.ilike(pattern), KnowledgeDocument.source_url.ilike(pattern))
        )
    if status == "excluded":
        filters.append(KnowledgeDocument.excluded.is_(True))
    elif status == "failed":
        filters.append(KnowledgeDocument.crawl_status == CrawlStatus.FAILED)
    elif status == "indexed":
        filters.append(
            KnowledgeDocument.crawl_status.in_([CrawlStatus.EXTRACTED, CrawlStatus.EMBEDDED]),
            KnowledgeDocument.excluded.is_(False),
        )

    total = await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(*filters))
    rows = await db.execute(
        select(KnowledgeDocument, _chunk_count())
        .where(*filters)
        .order_by(KnowledgeDocument.source_url)
        .limit(limit)
        .offset(offset)
    )
    return DocumentPage(items=[_list_item(d, n) for d, n in rows], total=total or 0)


async def _get_document(
    db: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> KnowledgeDocument:
    doc = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == organization_id,
        )
    )
    if doc is None:
        raise NotFound("Document")
    return doc


async def document_detail(
    db: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentDetail:
    doc = await _get_document(db, organization_id, document_id)
    chunks = list(
        await db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc.id)
            .order_by(KnowledgeChunk.chunk_index)
        )
    )
    item = _list_item(doc, len(chunks))
    return DocumentDetail(
        **item.model_dump(),
        content=doc.content,
        meta=doc.meta,
        chunks=[
            ChunkRead(
                id=c.id,
                chunk_index=c.chunk_index,
                heading=c.heading,
                content=c.content,
                token_count=c.token_count,
                embedded=c.embedding is not None,
            )
            for c in chunks
        ],
    )


async def create_manual_document(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, data: ManualDocumentCreate
) -> DocumentDetail:
    """Knowledge that isn't on the website (positioning notes, case studies…).

    Indexed inline: a single document is a few chunks and one embedding call.
    """
    doc = KnowledgeDocument(
        organization_id=organization_id,
        source_url=f"manual:{uuid.uuid4()}",
        document_type="manual",
        title=data.title,
        content=data.content,
        content_hash=content_hash(data.title, data.content),
        word_count=len(data.content.split()),
        last_crawled_at=datetime.now(UTC),
    )
    db.add(doc)
    await db.flush()
    await index_document(db, doc, get_embedding_provider())
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_DOCUMENT_ADDED,
        entity_type="knowledge_document",
        entity_id=doc.id,
        new_value={"title": data.title},
    )
    await db.commit()
    return await document_detail(db, organization_id, doc.id)


async def update_document(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    data: DocumentUpdate,
) -> DocumentDetail:
    doc = await _get_document(db, organization_id, document_id)
    changes = data.changes()
    if ({"title", "content"} & changes.keys()) and doc.document_type != "manual":
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Crawled pages are edited on your website; re-crawl to update them.",
        )
    old, new = audit.diff(doc, {k: v for k, v in changes.items() if k != "content"})
    content_changed = "content" in changes and changes["content"] != doc.content
    if content_changed:
        new["content"] = "(updated)"
    if not new:
        return await document_detail(db, organization_id, doc.id)

    for field, value in changes.items():
        setattr(doc, field, value)
    if doc.excluded:
        await clear_chunks(db, doc)
    elif content_changed or "title" in new or "excluded" in new:
        if doc.content:
            doc.content_hash = content_hash(doc.title, doc.content)
            doc.word_count = len(doc.content.split())
            await index_document(db, doc, get_embedding_provider())
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_DOCUMENT_UPDATED,
        entity_type="knowledge_document",
        entity_id=doc.id,
        old_value=old,
        new_value=new,
    )
    await db.commit()
    return await document_detail(db, organization_id, doc.id)


async def delete_document(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    doc = await _get_document(db, organization_id, document_id)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.KNOWLEDGE_DOCUMENT_DELETED,
        entity_type="knowledge_document",
        entity_id=doc.id,
        old_value={"title": doc.title, "url": doc.source_url},
    )
    await db.delete(doc)
    await db.commit()
