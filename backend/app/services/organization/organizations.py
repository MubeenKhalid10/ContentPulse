import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.permissions import Role
from app.models.design import CreativeAsset
from app.models.enums import MemberStatus
from app.models.organization import (
    BrandProfile,
    Organization,
    OrganizationMember,
    OrganizationService,
    OrganizationSettings,
)
from app.models.user import User
from app.schemas.organization import OrganizationCreate, ServiceCreate
from app.services import audit
from app.services.audit import AuditAction
from app.sources import DEFAULT_ENABLED_SOURCES
from app.storage import get_storage


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60].strip("-") or "org"


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    candidate = base
    while await db.scalar(select(Organization.id).where(Organization.slug == candidate)):
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate


async def create_organization(
    db: AsyncSession, user: User, data: OrganizationCreate
) -> Organization:
    """Create an organization with default settings/brand; creator becomes admin."""
    org = Organization(
        name=data.name,
        slug=await _unique_slug(db, data.name),
        website_url=data.website_url,
        description=data.description,
        industry=data.industry,
        timezone=data.timezone,
    )
    db.add(org)
    await db.flush()
    db.add(
        OrganizationSettings(
            organization_id=org.id,
            default_timezone=data.timezone,
            enabled_sources=list(DEFAULT_ENABLED_SOURCES),
        )
    )
    db.add(BrandProfile(organization_id=org.id))
    db.add(
        OrganizationMember(
            organization_id=org.id,
            user_id=user.id,
            role=Role.ADMIN,
            status=MemberStatus.ACTIVE,
            joined_at=datetime.now(UTC),
        )
    )
    audit.record(
        db,
        organization_id=org.id,
        user_id=user.id,
        action=AuditAction.ORGANIZATION_CREATED,
        entity_type="organization",
        entity_id=org.id,
        new_value=data.model_dump(),
    )
    try:
        await db.commit()
    except IntegrityError as exc:  # slug race with a concurrent create
        await db.rollback()
        raise Conflict("Could not create the organization, please retry.") from exc
    await db.refresh(org)
    return org


async def apply_changes[T](
    db: AsyncSession,
    obj: T,
    changes: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    action: AuditAction,
    entity_type: str,
    entity_id: uuid.UUID,
) -> T:
    """Apply a PATCH, audit only fields that changed, and commit."""
    old, new = audit.diff(obj, changes)
    if new:
        for field, value in changes.items():
            setattr(obj, field, value)
        audit.record(
            db,
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old,
            new_value=new,
        )
        await db.commit()
        await db.refresh(obj)
    return obj


async def delete_organization(db: AsyncSession, organization: Organization) -> None:
    """Delete an organization and remove its uploaded creative objects."""
    assets = list(
        await db.scalars(
            select(CreativeAsset).where(CreativeAsset.organization_id == organization.id)
        )
    )
    storage = get_storage()
    for asset in assets:
        await storage.delete(asset.storage_key)

    await db.delete(organization)
    await db.commit()


async def get_settings(db: AsyncSession, organization_id: uuid.UUID) -> OrganizationSettings:
    row = await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )
    if row is None:
        raise NotFound("Organization settings")
    return row


async def get_brand(db: AsyncSession, organization_id: uuid.UUID) -> BrandProfile:
    row = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == organization_id)
    )
    if row is None:
        raise NotFound("Brand profile")
    return row


async def list_services(db: AsyncSession, organization_id: uuid.UUID) -> list[OrganizationService]:
    rows = await db.scalars(
        select(OrganizationService)
        .where(OrganizationService.organization_id == organization_id)
        .order_by(OrganizationService.kind, OrganizationService.name)
    )
    return list(rows)


async def get_service(
    db: AsyncSession, organization_id: uuid.UUID, service_id: uuid.UUID
) -> OrganizationService:
    # Always filter by organization_id: never trust the id alone (spec §61).
    service = await db.scalar(
        select(OrganizationService).where(
            OrganizationService.id == service_id,
            OrganizationService.organization_id == organization_id,
        )
    )
    if service is None:
        raise NotFound("Service")
    return service


async def create_service(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, data: ServiceCreate
) -> OrganizationService:
    service = OrganizationService(organization_id=organization_id, **data.model_dump())
    db.add(service)
    await db.flush()
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.SERVICE_CREATED,
        entity_type="organization_service",
        entity_id=service.id,
        new_value=data.model_dump(),
    )
    await db.commit()
    await db.refresh(service)
    return service


async def delete_service(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, service_id: uuid.UUID
) -> None:
    service = await get_service(db, organization_id, service_id)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.SERVICE_DELETED,
        entity_type="organization_service",
        entity_id=service.id,
        old_value={"name": service.name, "kind": service.kind},
    )
    await db.delete(service)
    await db.commit()
