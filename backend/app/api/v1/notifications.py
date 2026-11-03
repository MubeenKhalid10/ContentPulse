import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.schemas.notification import NotificationPage
from app.services import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Every member reads only their own notifications.
Member = Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))]


@router.get("", response_model=NotificationPage)
async def list_notifications(ctx: Member, db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 30):
    return await notifications.list_for(db, ctx.organization_id, ctx.user.id, limit=limit)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(ctx: Member, db: DB):
    await notifications.mark_all_read(db, ctx.organization_id, ctx.user.id)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(notification_id: uuid.UUID, ctx: Member, db: DB):
    await notifications.mark_read(db, ctx.organization_id, ctx.user.id, notification_id)
