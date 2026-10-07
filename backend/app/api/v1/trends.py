import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    DB,
    AppSettings,
    OrgContext,
    active_org_any_permission,
    active_org_permission,
)
from app.core.permissions import Permission
from app.core.ratelimit import AI_PER_USER, per_user
from app.models.enums import TrendStatus
from app.schemas.trend import (
    AnalyzeStarted,
    DiscoverRequest,
    MarketOption,
    RelevanceOverride,
    RunRead,
    RunStarted,
    SourceInfo,
    SourceToggle,
    TrendDetail,
    TrendPage,
)
from app.services.trends import service
from app.sources.locations import supported_markets

AI_LIMIT = per_user(AI_PER_USER)
router = APIRouter(prefix="/trends", tags=["trends"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.TRENDS_READ))]
CanManage = Annotated[OrgContext, Depends(active_org_permission(Permission.TRENDS_MANAGE))]
# Reviewing trends is part of the content manager's topic workflow (spec §20).
CanReview = Annotated[
    OrgContext,
    Depends(active_org_any_permission(Permission.TRENDS_MANAGE, Permission.TOPICS_MANAGE)),
]


@router.get("/sources", response_model=list[SourceInfo])
async def list_sources(ctx: CanRead, db: DB, settings: AppSettings):
    return await service.list_sources(db, ctx.organization_id, settings)


@router.patch("/sources/{key}", response_model=list[SourceInfo])
async def toggle_source(
    key: str, data: SourceToggle, ctx: CanManage, db: DB, settings: AppSettings
):
    await service.set_source_enabled(db, ctx.organization_id, ctx.user.id, key, data.enabled)
    return await service.list_sources(db, ctx.organization_id, settings)


@router.get("/markets", response_model=list[MarketOption])
async def markets(ctx: CanRead):
    return supported_markets()


@router.post(
    "/discover",
    response_model=RunStarted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def discover(data: DiscoverRequest, ctx: CanManage, db: DB):
    run = await service.start_discovery(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        sources=data.sources,
        locations=data.locations,
    )
    return RunStarted(run_id=run.id, status=run.status, run=RunRead.model_validate(run))


@router.get("/runs", response_model=list[RunRead])
async def list_runs(ctx: CanRead, db: DB, limit: Annotated[int, Query(ge=1, le=50)] = 10):
    return await service.list_runs(db, ctx.organization_id, limit)


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.get_run(db, ctx.organization_id, run_id)


@router.get("", response_model=TrendPage)
async def list_trends(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal["active", "shortlisted", "rejected", "archived", "all"], Query(alias="status")
    ] = "active",
    source: Annotated[str | None, Query(max_length=40)] = None,
    location: Annotated[str | None, Query(max_length=10)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: Literal["score", "recent", "mentions", "new"] = "score",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    relevance: Literal[
        "relevant", "highly_relevant", "weakly_relevant", "not_relevant", "unanalyzed"
    ]
    | None = None,
):
    return await service.list_trends(
        db,
        ctx.organization_id,
        status=status_filter,
        source=source,
        location=location,
        q=q,
        min_score=min_score,
        sort=sort,
        limit=limit,
        offset=offset,
        relevance=relevance,
    )


@router.get("/{trend_id}", response_model=TrendDetail)
async def get_trend(trend_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.trend_detail(db, ctx.organization_id, trend_id)


@router.post(
    "/{trend_id}/analyze",
    response_model=AnalyzeStarted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def analyze(trend_id: uuid.UUID, ctx: CanReview, db: DB):
    job = await service.request_analysis(db, ctx.organization_id, ctx.user.id, trend_id)
    return AnalyzeStarted(job_id=job.id, status=job.status)


@router.patch("/{trend_id}/relevance", response_model=TrendDetail)
async def override_relevance(trend_id: uuid.UUID, data: RelevanceOverride, ctx: CanReview, db: DB):
    return await service.override_relevance(
        db, ctx.organization_id, ctx.user.id, trend_id, data.relevance_level
    )


@router.post("/{trend_id}/shortlist", response_model=TrendDetail)
async def shortlist(trend_id: uuid.UUID, ctx: CanReview, db: DB):
    return await service.transition(
        db, ctx.organization_id, ctx.user.id, trend_id, TrendStatus.SHORTLISTED
    )


@router.post("/{trend_id}/reject", response_model=TrendDetail)
async def reject(trend_id: uuid.UUID, ctx: CanReview, db: DB):
    return await service.transition(
        db, ctx.organization_id, ctx.user.id, trend_id, TrendStatus.REJECTED
    )


@router.post("/{trend_id}/restore", response_model=TrendDetail)
async def restore(trend_id: uuid.UUID, ctx: CanReview, db: DB):
    return await service.transition(db, ctx.organization_id, ctx.user.id, trend_id, TrendStatus.NEW)
