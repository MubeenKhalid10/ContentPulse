import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import DB, AppSettings, CurrentUser, OrgContext, org_permission
from app.core.errors import Forbidden
from app.core.permissions import Permission, Role
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.organization import (
    AuditLogRead,
    BrandRead,
    BrandUpdate,
    InviteCreate,
    InviteResponse,
    MemberRead,
    MemberUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    SettingsRead,
    SettingsUpdate,
)
from app.services import auth as auth_service
from app.services.audit import AuditAction
from app.services.organization import organizations as org_service
from app.services.organization import team as team_service
from app.services.topics.sync import FIT_SETTINGS, refresh_platform_fit

router = APIRouter(prefix="/organizations", tags=["organizations"])

CanRead = Annotated[OrgContext, Depends(org_permission(Permission.ORGANIZATION_READ))]
CanWrite = Annotated[OrgContext, Depends(org_permission(Permission.ORGANIZATION_WRITE))]
CanManageUsers = Annotated[OrgContext, Depends(org_permission(Permission.USERS_MANAGE))]


# --- Organizations ----------------------------------------------------------
@router.get("", response_model=list[OrganizationRead])
async def list_organizations(user: CurrentUser, db: DB):
    return [org for _, org in await auth_service.active_memberships(db, user.id)]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(data: OrganizationCreate, user: CurrentUser, db: DB):
    return await org_service.create_organization(db, user, data)


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(ctx: CanRead):
    return ctx.organization


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(data: OrganizationUpdate, ctx: CanWrite, db: DB):
    return await org_service.apply_changes(
        db,
        ctx.organization,
        data.changes(),
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        action=AuditAction.ORGANIZATION_UPDATED,
        entity_type="organization",
        entity_id=ctx.organization_id,
    )


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(ctx: CanWrite, db: DB) -> None:
    if ctx.role != Role.ADMIN:
        raise Forbidden("Only organization admins can delete a workspace.")
    await org_service.delete_organization(db, ctx.organization)


# --- Settings ---------------------------------------------------------------
@router.get("/{organization_id}/settings", response_model=SettingsRead)
async def get_settings(ctx: CanRead, db: DB):
    return await org_service.get_settings(db, ctx.organization_id)


@router.patch("/{organization_id}/settings", response_model=SettingsRead)
async def update_settings(data: SettingsUpdate, ctx: CanWrite, db: DB):
    settings = await org_service.get_settings(db, ctx.organization_id)
    changes = data.changes()
    updated = await org_service.apply_changes(
        db,
        settings,
        changes,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="organization_settings",
        entity_id=settings.id,
    )
    if FIT_SETTINGS & changes.keys():
        # e.g. Blog was just enabled: existing topics get scored for it too.
        await refresh_platform_fit(db, ctx.organization_id)
        await db.refresh(updated)
    return updated


# --- Brand ------------------------------------------------------------------
@router.get("/{organization_id}/brand", response_model=BrandRead)
async def get_brand(ctx: CanRead, db: DB):
    return await org_service.get_brand(db, ctx.organization_id)


@router.patch("/{organization_id}/brand", response_model=BrandRead)
async def update_brand(data: BrandUpdate, ctx: CanWrite, db: DB):
    brand = await org_service.get_brand(db, ctx.organization_id)
    return await org_service.apply_changes(
        db,
        brand,
        data.changes(),
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        action=AuditAction.BRAND_UPDATED,
        entity_type="brand_profile",
        entity_id=brand.id,
    )


# --- Services / products / expertise ----------------------------------------
@router.get("/{organization_id}/services", response_model=list[ServiceRead])
async def list_services(ctx: CanRead, db: DB):
    return await org_service.list_services(db, ctx.organization_id)


@router.post(
    "/{organization_id}/services",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_service(data: ServiceCreate, ctx: CanWrite, db: DB):
    return await org_service.create_service(db, ctx.organization_id, ctx.user.id, data)


@router.patch("/{organization_id}/services/{service_id}", response_model=ServiceRead)
async def update_service(service_id: uuid.UUID, data: ServiceUpdate, ctx: CanWrite, db: DB):
    service = await org_service.get_service(db, ctx.organization_id, service_id)
    return await org_service.apply_changes(
        db,
        service,
        data.changes(),
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        action=AuditAction.SERVICE_UPDATED,
        entity_type="organization_service",
        entity_id=service.id,
    )


@router.delete("/{organization_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: uuid.UUID, ctx: CanWrite, db: DB) -> None:
    await org_service.delete_service(db, ctx.organization_id, ctx.user.id, service_id)


# --- Team -------------------------------------------------------------------
@router.get("/{organization_id}/members", response_model=list[MemberRead])
async def list_members(ctx: CanRead, db: DB):
    return await team_service.list_members(db, ctx.organization_id)


@router.post(
    "/{organization_id}/invitations",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(data: InviteCreate, ctx: CanManageUsers, db: DB, settings: AppSettings):
    return await team_service.invite_member(
        db,
        organization_id=ctx.organization_id,
        inviter_id=ctx.user.id,
        data=data,
        settings=settings,
    )


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberRead)
async def update_member(member_id: uuid.UUID, data: MemberUpdate, ctx: CanManageUsers, db: DB):
    return await team_service.update_member(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user.id,
        member_id=member_id,
        data=data,
    )


@router.delete("/{organization_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: uuid.UUID, ctx: CanManageUsers, db: DB) -> None:
    await team_service.remove_member(
        db, organization_id=ctx.organization_id, actor_id=ctx.user.id, member_id=member_id
    )


# --- Audit history ----------------------------------------------------------
@router.get("/{organization_id}/audit-logs", response_model=list[AuditLogRead])
async def list_audit_logs(
    ctx: CanWrite,
    db: DB,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    before: Annotated[datetime | None, Query(description="Cursor: created_at of last item")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    query = (
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.organization_id == ctx.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if before:
        query = query.where(AuditLog.created_at < before)
    rows = await db.execute(query)
    return [
        AuditLogRead.model_validate(log).model_copy(update={"user_name": name})
        for log, name in rows
    ]
