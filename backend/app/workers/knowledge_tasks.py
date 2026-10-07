"""Knowledge base background jobs: website crawl and re-index (spec §9, §44)."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.enums import CrawlStatus, KnowledgeJobStatus
from app.models.knowledge import KnowledgeCrawlJob, KnowledgeDocument
from app.services.knowledge.crawler import PageResult, SiteCrawler
from app.services.knowledge.fetcher import (
    Resolver,
    SafeFetcher,
    build_http_client,
    system_resolver,
)
from app.services.knowledge.indexer import clear_chunks, content_hash, index_document
from app.services.knowledge.urls import in_scope

# Pages with less text than this (contact forms, stubs) are not indexed.
MIN_WORDS = 40
# A running job whose heartbeat is older than this is assumed dead.
STALE_AFTER = timedelta(minutes=3)

# Seams so tests can crawl a fake site without network access.
http_client_factory: Callable[[Settings], httpx.AsyncClient] = build_http_client
resolver: Resolver = system_resolver


class _Cancelled(Exception):
    pass


class JobFailed(Exception):
    """Ends a job as failed with a message shown to the user."""


class _EmbeddingState:
    """Stops calling a failing embedding provider for the rest of the job."""

    def __init__(self, provider: EmbeddingProvider | None) -> None:
        self.provider = provider
        self.warning: str | None = None

    def disable(self, error: EmbeddingError) -> None:
        self.provider = None
        self.warning = (
            f"Semantic indexing paused ({error}). Pages were indexed for keyword search; "
            "re-index once the embedding provider is working."
        )


def _now() -> datetime:
    return datetime.now(UTC)


async def _finish(
    job_id: uuid.UUID,
    status: KnowledgeJobStatus,
    *,
    error: str | None = None,
    warning: str | None = None,
) -> None:
    async with SessionLocal() as db:
        job = await db.get(KnowledgeCrawlJob, job_id)
        if job is None:
            return
        job.status = status
        job.error = error
        if warning and warning not in job.warnings:
            job.warnings = [*job.warnings, warning]
        job.finished_at = _now()
        job.heartbeat_at = job.finished_at
        await db.commit()


async def _start(job_id: uuid.UUID) -> KnowledgeCrawlJob | None:
    async with SessionLocal() as db:
        job = await db.get(KnowledgeCrawlJob, job_id)
        if job is None or job.status != KnowledgeJobStatus.QUEUED:
            return None
        if job.cancel_requested:
            job.status = KnowledgeJobStatus.CANCELLED
            job.finished_at = _now()
            await db.commit()
            return None
        job.status = KnowledgeJobStatus.RUNNING
        job.started_at = job.heartbeat_at = _now()
        await db.commit()
        return job


async def _run(
    job_id: uuid.UUID, body: Callable[[KnowledgeCrawlJob], Awaitable[str | None]]
) -> None:
    """Shared lifecycle: start, run, record success/cancel/failure."""
    job = await _start(job_id)
    if job is None:
        return
    try:
        warning = await body(job)
    except _Cancelled:
        await _finish(job_id, KnowledgeJobStatus.CANCELLED)
    except JobFailed as exc:
        await _finish(job_id, KnowledgeJobStatus.FAILED, error=str(exc))
    except asyncio.CancelledError:
        await asyncio.shield(
            _finish(job_id, KnowledgeJobStatus.FAILED, error="Interrupted: the server shut down.")
        )
        raise
    except Exception:
        logger.exception("Knowledge job %s failed", job_id)
        await _finish(job_id, KnowledgeJobStatus.FAILED, error="The job failed unexpectedly.")
    else:
        await _finish(job_id, KnowledgeJobStatus.SUCCEEDED, warning=warning)


async def _checkpoint(db: AsyncSession, job: KnowledgeCrawlJob) -> None:
    """Heartbeat + honour cancellation. Call once per unit of work."""
    await db.refresh(job, attribute_names=["cancel_requested"])
    if job.cancel_requested:
        raise _Cancelled
    job.heartbeat_at = _now()


# --- Crawl ----------------------------------------------------------------
async def _store_page(
    db: AsyncSession, job: KnowledgeCrawlJob, result: PageResult, embeddings: _EmbeddingState
) -> str:
    """Persist one crawled page. Returns indexed|unchanged|skipped|failed."""
    org_id = job.organization_id
    url = result.final_url or result.url

    async def find(source_url: str) -> KnowledgeDocument | None:
        return await db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.organization_id == org_id,
                KnowledgeDocument.source_url == source_url,
            )
        )

    if result.error:
        if result.status_code in (404, 410):
            doc = await find(url)
            if doc and not doc.excluded:
                await clear_chunks(db, doc)
                doc.crawl_status = CrawlStatus.FAILED
                doc.crawl_error = f"Page no longer exists (HTTP {result.status_code})."
                doc.last_crawl_job_id = job.id
        return "failed"
    if result.skipped or result.page is None:
        return "skipped"

    page = result.page
    key = (
        page.canonical_url
        if page.canonical_url and in_scope(page.canonical_url, job.root_url or url)
        else url
    )
    doc = await find(key)
    if doc is not None and doc.excluded:
        return "skipped"
    if page.noindex or page.word_count < MIN_WORDS:
        if doc is not None and page.noindex:
            await db.delete(doc)  # the site owner asked not to index it
        return "skipped"

    digest = content_hash(page.title, page.markdown)
    if doc is None:
        duplicate = await db.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.organization_id == org_id,
                KnowledgeDocument.content_hash == digest,
            )
        )
        if duplicate:
            return "unchanged"  # same page reachable under another URL
        doc = KnowledgeDocument(organization_id=org_id, source_url=key, document_type="web_page")
        db.add(doc)
        await db.flush()
    elif doc.content_hash == digest and (
        doc.crawl_status == CrawlStatus.EMBEDDED
        or (doc.crawl_status == CrawlStatus.EXTRACTED and embeddings.provider is None)
    ):
        doc.last_crawled_at = _now()
        doc.last_crawl_job_id = job.id
        return "unchanged"

    doc.title = page.title
    doc.content = page.markdown
    doc.content_hash = digest
    doc.word_count = page.word_count
    doc.meta = {
        "description": page.description,
        "language": page.language,
        "headings": page.headings,
        "fetched_url": url,
        "http_status": result.status_code,
    }
    doc.last_crawled_at = _now()
    doc.last_crawl_job_id = job.id
    outcome = await index_document(db, doc, embeddings.provider)
    if outcome.embedding_error:
        embeddings.disable(outcome.embedding_error)
    job.chunks_created += outcome.chunks
    return "indexed"


async def _crawl(job: KnowledgeCrawlJob) -> str | None:
    settings = get_settings()
    embeddings = _EmbeddingState(get_embedding_provider(settings))
    async with SessionLocal() as db:
        excluded = set(
            await db.scalars(
                select(KnowledgeDocument.source_url).where(
                    KnowledgeDocument.organization_id == job.organization_id,
                    KnowledgeDocument.excluded.is_(True),
                )
            )
        )

    first_error: str | None = None
    async with http_client_factory(settings) as client:
        crawler = SiteCrawler(
            SafeFetcher(client, settings, resolver),
            job.root_url or "",
            max_pages=job.max_pages,
            concurrency=settings.crawler_concurrency,
            user_agent=settings.crawler_user_agent,
            skip_urls=excluded,
        )
        async for result in crawler.crawl():
            async with SessionLocal() as db:
                current = await db.get(KnowledgeCrawlJob, job.id)
                assert current is not None
                await _checkpoint(db, current)
                outcome = await _store_page(db, current, result, embeddings)
                current.pages_crawled += 1
                current.pages_discovered = crawler.stats.discovered
                if outcome == "indexed":
                    current.pages_indexed += 1
                elif outcome == "unchanged":
                    current.pages_unchanged += 1
                elif outcome == "skipped":
                    current.pages_skipped += 1
                else:
                    current.pages_failed += 1
                    first_error = first_error or f"{result.url}: {result.error}"
                await db.commit()

    async with SessionLocal() as db:
        final = await db.get(KnowledgeCrawlJob, job.id)
        assert final is not None
        final.pages_discovered = crawler.stats.discovered
        if crawler.stats.warnings:
            final.warnings = [*final.warnings, *crawler.stats.warnings]
        useful = final.pages_indexed + final.pages_unchanged
        await db.commit()

    if useful == 0:
        if crawler.stats.warnings:
            raise JobFailed(crawler.stats.warnings[0])
        if first_error:
            raise JobFailed(f"Could not read the website. First error: {first_error}")
        raise JobFailed("No pages with enough text to index were found.")
    return embeddings.warning


async def run_crawl_job(job_id: uuid.UUID) -> None:
    await _run(job_id, _crawl)


# --- Re-index ---------------------------------------------------------------
async def _reindex(job: KnowledgeCrawlJob) -> str | None:
    embeddings = _EmbeddingState(get_embedding_provider())
    async with SessionLocal() as db:
        ids = list(
            await db.scalars(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.organization_id == job.organization_id,
                    KnowledgeDocument.excluded.is_(False),
                    KnowledgeDocument.content.is_not(None),
                )
            )
        )
        current = await db.get(KnowledgeCrawlJob, job.id)
        assert current is not None
        current.pages_discovered = len(ids)
        await db.commit()

    for doc_id in ids:
        async with SessionLocal() as db:
            current = await db.get(KnowledgeCrawlJob, job.id)
            doc = await db.get(KnowledgeDocument, doc_id)
            assert current is not None
            await _checkpoint(db, current)
            if doc is not None:
                outcome = await index_document(db, doc, embeddings.provider)
                if outcome.embedding_error:
                    embeddings.disable(outcome.embedding_error)
                current.chunks_created += outcome.chunks
                current.pages_indexed += 1
            current.pages_crawled += 1
            await db.commit()
    return embeddings.warning


async def run_reindex_job(job_id: uuid.UUID) -> None:
    await _run(job_id, _reindex)


# --- Recovery ---------------------------------------------------------------
def stale_condition():
    cutoff = _now() - STALE_AFTER
    return or_(
        KnowledgeCrawlJob.heartbeat_at < cutoff,
        (KnowledgeCrawlJob.heartbeat_at.is_(None)) & (KnowledgeCrawlJob.created_at < cutoff),
    )


async def recover_stale_jobs() -> int:
    """Fail jobs whose worker died (e.g. the process restarted mid-crawl)."""
    async with SessionLocal() as db:
        result = await db.execute(
            update(KnowledgeCrawlJob)
            .where(
                KnowledgeCrawlJob.status.in_(
                    [KnowledgeJobStatus.QUEUED, KnowledgeJobStatus.RUNNING]
                ),
                stale_condition(),
            )
            .values(
                status=KnowledgeJobStatus.FAILED,
                error="Interrupted: the server restarted. Start the crawl again.",
                finished_at=_now(),
            )
        )
        await db.commit()
        return result.rowcount or 0
