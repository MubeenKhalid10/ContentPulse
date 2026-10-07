import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.ai.embeddings import get_embedding_provider
from app.api.deps import DB, AppSettings, OrgContext, org_permission
from app.core.permissions import Permission
from app.schemas.knowledge import (
    CrawlRequest,
    DocumentDetail,
    DocumentPage,
    DocumentUpdate,
    JobRead,
    JobStarted,
    KnowledgeSummary,
    ManualDocumentCreate,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.knowledge import service
from app.services.knowledge.search import search_knowledge

router = APIRouter(prefix="/organizations/{organization_id}/knowledge", tags=["knowledge"])

CanRead = Annotated[OrgContext, Depends(org_permission(Permission.KNOWLEDGE_READ))]
CanWrite = Annotated[OrgContext, Depends(org_permission(Permission.KNOWLEDGE_WRITE))]


def _started(job) -> JobStarted:
    return JobStarted(job_id=job.id, status=job.status, job=JobRead.model_validate(job))


@router.get("/summary", response_model=KnowledgeSummary)
async def get_summary(ctx: CanRead, db: DB, settings: AppSettings):
    return await service.summary(db, ctx.organization, settings)


@router.post("/crawl", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def crawl(data: CrawlRequest, ctx: CanWrite, db: DB, settings: AppSettings):
    job = await service.start_crawl(
        db,
        organization=ctx.organization,
        user_id=ctx.user.id,
        url=data.url,
        max_pages=data.max_pages,
        settings=settings,
    )
    return _started(job)


@router.post("/reindex", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def reindex(ctx: CanWrite, db: DB):
    job = await service.start_reindex(db, organization_id=ctx.organization_id, user_id=ctx.user.id)
    return _started(job)


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(ctx: CanRead, db: DB, limit: Annotated[int, Query(ge=1, le=50)] = 10):
    return await service.list_jobs(db, ctx.organization_id, limit)


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.get_job(db, ctx.organization_id, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: uuid.UUID, ctx: CanWrite, db: DB):
    return await service.cancel_job(db, ctx.organization_id, job_id, ctx.user.id)


@router.get("/documents", response_model=DocumentPage)
async def list_documents(
    ctx: CanRead,
    db: DB,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        Literal["indexed", "failed", "excluded"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_documents(
        db, ctx.organization_id, q=q, status=status_filter, limit=limit, offset=offset
    )


@router.post("/documents", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def create_document(data: ManualDocumentCreate, ctx: CanWrite, db: DB):
    return await service.create_manual_document(db, ctx.organization_id, ctx.user.id, data)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.document_detail(db, ctx.organization_id, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentDetail)
async def update_document(document_id: uuid.UUID, data: DocumentUpdate, ctx: CanWrite, db: DB):
    return await service.update_document(db, ctx.organization_id, ctx.user.id, document_id, data)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, ctx: CanWrite, db: DB) -> None:
    await service.delete_document(db, ctx.organization_id, ctx.user.id, document_id)


@router.post("/search", response_model=SearchResponse)
async def search(data: SearchRequest, ctx: CanRead, db: DB, settings: AppSettings):
    hits, semantic = await search_knowledge(
        db,
        ctx.organization_id,
        data.query,
        limit=data.limit,
        provider=get_embedding_provider(settings),
        min_similarity=settings.knowledge_min_similarity,
    )
    return SearchResponse(
        mode="hybrid" if semantic else "keyword",
        results=[
            SearchResult(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                title=h.title,
                url=h.url,
                document_type=h.document_type,
                heading=h.heading,
                snippet=h.snippet,
                score=h.score,
                match=h.match,
            )
            for h in hits
        ],
    )
