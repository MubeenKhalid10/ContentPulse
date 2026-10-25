from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.schemas.dashboard import Attention, DashboardOverview, DashboardSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    ctx: Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))],
    db: DB,
) -> DashboardSummary:
    return await dashboard_service.summary(db, ctx.organization_id)


@router.get("/attention", response_model=Attention)
async def attention(
    ctx: Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))],
    db: DB,
) -> Attention:
    """Small counts for the sidebar badges; the full summary is only for the dashboard."""
    return await dashboard_service.attention(db, ctx.organization_id)


@router.get("/overview", response_model=DashboardOverview)
async def overview(
    ctx: Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))],
    db: DB,
    days: Annotated[int, Query(description="Period length: 7, 30 or 90 days")] = 7,
) -> DashboardOverview:
    return await dashboard_service.overview(db, ctx.organization_id, days)
