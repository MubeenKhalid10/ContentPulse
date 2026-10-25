import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

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
    DiscoveryWindowRead,
    ExportWindowRead,
    MarketOption,
    RelevanceOverride,
    RunRead,
    RunStarted,
    SourceInfo,
    SourceToggle,
    TrendDetail,
    TrendPage,
)
from app.services.trends import export, service
from app.sources.locations import supported_markets

AI_LIMIT = per_user(AI_PER_USER)
router = APIRouter(prefix="/trends", tags=["trends"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.TRENDS_READ))]
CanManage = Annotated[OrgContext, Depends(active_org_permission(Permission.TRENDS_MANAGE))]
CanExport = Annotated[OrgContext, Depends(active_org_permission(Permission.TRENDS_EXPORT))]
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


def _window_read(window: service.DiscoveryWindow) -> DiscoveryWindowRead:
    last = window.last_run
    return DiscoveryWindowRead(
        background=window.background,
        last_discovery_at=(last.finished_at or last.created_at) if last else None,
        next_discovery_at=window.next_discovery_at,
        can_discover=window.can_discover,
        new_trends=last.trends_created if last else 0,
    )


@router.get("/discovery", response_model=DiscoveryWindowRead)
async def discovery_status(ctx: CanRead, db: DB, settings: AppSettings):
    return _window_read(await service.discovery_window(db, ctx.organization_id, settings))


@router.post(
    "/discover",
    response_model=RunStarted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def discover(
    data: DiscoverRequest, ctx: CanManage, db: DB, settings: AppSettings, response: Response
):
    """Collect new trends, at most once per discovery window. Inside the
    window nothing is collected (no provider calls): the answer points at the
    stored trends and says when the next discovery is due."""
    window = await service.discovery_window(db, ctx.organization_id, settings)
    if not window.can_discover and window.last_run is not None:
        response.status_code = status.HTTP_200_OK
        run = window.last_run
        return RunStarted(
            started=False,
            run_id=run.id,
            status=run.status,
            run=RunRead.model_validate(run),
            window=_window_read(window),
        )
    run = await service.start_discovery(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        sources=data.sources,
        locations=data.locations,
    )
    return RunStarted(
        run_id=run.id,
        status=run.status,
        run=RunRead.model_validate(run),
        window=_window_read(window),
    )


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
        Literal["active", "unshortlisted", "shortlisted", "rejected", "archived", "all"],
        Query(alias="status"),
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
    # Only trends seen in the last N days (the /trends page uses 7). Older
    # trends are hidden, not deleted.
    seen_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
):
    seen_since = datetime.now(UTC) - timedelta(days=seen_within_days) if seen_within_days else None
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
        seen_since=seen_since,
    )


def _export_window_read(window: export.ExportWindow) -> ExportWindowRead:
    return ExportWindowRead(
        organization_id=window.organization_id,
        organization_name=window.organization_name,
        timezone=window.timezone,
        start=window.local_start,
        end=window.local_end,
        filename=window.filename,
    )


@router.get("/export/window", response_model=ExportWindowRead)
async def export_window(ctx: CanExport, db: DB):
    """The range the CSV would cover now (admins only)."""
    return _export_window_read(await export.export_window(db, ctx.organization_id))


@router.get(
    "/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_csv(ctx: CanExport, db: DB) -> Response:
    """The active organization's trends last seen in the last seven days, as
    CSV (admins only). The range is captured once, here, and is the same in
    the query, the filename and the X-Export-* headers."""
    window = await export.export_window(db, ctx.organization_id)
    rows = await export.export_rows(db, window)
    return Response(
        content=export.to_csv(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{window.filename}"',
            "Cache-Control": "no-store",
            "X-Export-Start": window.local_start.isoformat(),
            "X-Export-End": window.local_end.isoformat(),
            "X-Export-Timezone": window.timezone,
            "X-Export-Rows": str(len(rows)),
        },
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


@router.delete("/{trend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trend(trend_id: uuid.UUID, ctx: CanReview, db: DB) -> None:
    await service.delete_trend(db, ctx.organization_id, ctx.user.id, trend_id)


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
