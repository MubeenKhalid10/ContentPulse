from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    ctx: Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))],
    db: DB,
) -> DashboardSummary:
    return await dashboard_service.summary(db, ctx.organization_id)
