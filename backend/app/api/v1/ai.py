import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select

from app.ai.provider import get_ai_provider
from app.api.deps import DB, AppSettings, CurrentUser, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.models.ai import LLMRequest
from app.schemas.trend import AIStatus, LLMRequestRead, LLMUsage, LLMUsageGroup

router = APIRouter(prefix="/ai", tags=["ai"])

CanSeeUsage = Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_WRITE))]


@router.get("/status", response_model=AIStatus)
async def ai_status(user: CurrentUser, settings: AppSettings) -> AIStatus:
    """Which analysis engine is active. Never exposes keys."""
    provider = get_ai_provider(settings)
    return AIStatus(
        configured=provider is not None,
        engine="ai" if provider else "rules",
        provider=provider.name if provider else None,
        model=provider.model if provider else None,
        chain=provider.chain if provider else [],
    )


@router.get("/usage", response_model=LLMUsage)
async def ai_usage(
    ctx: CanSeeUsage,
    db: DB,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    job_id: uuid.UUID | None = None,
) -> LLMUsage:
    """Model requests made for this organization: counts, tokens, retries,
    fallbacks and latency by workflow and model. With `job_id`, also every
    request that one job made."""
    since = datetime.now(UTC) - timedelta(days=days)
    scope = [LLMRequest.organization_id == ctx.organization_id, LLMRequest.created_at >= since]
    if job_id:
        scope.append(LLMRequest.job_id == job_id)

    def count(status: str):
        return func.sum(case((LLMRequest.status == status, 1), else_=0))

    rows = await db.execute(
        select(
            LLMRequest.workflow,
            LLMRequest.provider,
            LLMRequest.model,
            func.count().label("records"),
            count("succeeded").label("succeeded"),
            count("failed").label("failed"),
            count("cached").label("cached"),
            func.sum(case((LLMRequest.retry_count > 0, 1), else_=0)).label("retries"),
            func.sum(case((LLMRequest.fallback_used, 1), else_=0)).label("fallbacks"),
            func.coalesce(func.sum(LLMRequest.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(LLMRequest.output_tokens), 0).label("output_tokens"),
            func.avg(LLMRequest.latency_ms).filter(LLMRequest.status != "cached").label("latency"),
            func.avg(LLMRequest.queue_wait_ms).filter(LLMRequest.status != "cached").label("wait"),
            func.max(LLMRequest.queue_wait_ms).label("max_wait"),
        )
        .where(*scope)
        .group_by(LLMRequest.workflow, LLMRequest.provider, LLMRequest.model)
        .order_by(func.count().desc())
    )
    groups = [
        LLMUsageGroup(
            workflow=r.workflow,
            provider=r.provider,
            model=r.model,
            requests=int(r.succeeded) + int(r.failed),
            succeeded=int(r.succeeded),
            failed=int(r.failed),
            cached=int(r.cached),
            retries=int(r.retries),
            fallbacks=int(r.fallbacks),
            input_tokens=int(r.input_tokens),
            output_tokens=int(r.output_tokens),
            avg_latency_ms=round(r.latency) if r.latency is not None else None,
            avg_queue_wait_ms=round(r.wait) if r.wait is not None else None,
            max_queue_wait_ms=int(r.max_wait or 0),
        )
        for r in rows
    ]
    requests: list[LLMRequestRead] = []
    if job_id:
        requests = [
            LLMRequestRead.model_validate(r)
            for r in await db.scalars(
                select(LLMRequest).where(*scope).order_by(LLMRequest.started_at)
            )
        ]
    return LLMUsage(
        since=since,
        requests_total=sum(g.requests for g in groups),
        cached_total=sum(g.cached for g in groups),
        groups=groups,
        requests=requests,
    )
