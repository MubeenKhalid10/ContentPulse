"""Request-scoped dependencies: authentication, tenant context, RBAC.

Every organization-scoped route resolves an OrgContext, which proves the
caller is an active member of that organization (spec §61). Non-members get
404 rather than 403 so organization ids cannot be probed.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.permissions import Permission, Role, has_permission
from app.db.session import get_db
from app.models.enums import MemberStatus
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.services import auth as auth_service

DB = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _extract_token(request: Request, settings: Settings) -> str | None:
    header = request.headers.get("authorization")
    if header:
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return request.cookies.get(settings.session_cookie_name)


async def get_optional_user(request: Request, db: DB, settings: AppSettings) -> User | None:
    token = _extract_token(request, settings)
    if not token:
        return None
    return await auth_service.user_from_token(db, token, settings)


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise Unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


@dataclass(frozen=True)
class OrgContext:
    user: User
    organization: Organization
    membership: OrganizationMember

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def role(self) -> Role:
        return self.membership.role

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise Forbidden()


async def load_org_context(db: AsyncSession, user: User, organization_id: uuid.UUID) -> OrgContext:
    row = (
        await db.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
        )
    ).first()
    if row is None:
        raise NotFound("Organization")
    membership, organization = row
    return OrgContext(user=user, organization=organization, membership=membership)


def org_permission(permission: Permission):
    """For routes under /organizations/{organization_id}/..."""

    async def dependency(organization_id: uuid.UUID, user: CurrentUser, db: DB) -> OrgContext:
        ctx = await load_org_context(db, user, organization_id)
        ctx.require(permission)
        return ctx

    return dependency


def active_org_any_permission(*permissions: Permission):
    """Active-org route allowed when the caller has any of `permissions`."""

    async def dependency(
        user: CurrentUser,
        db: DB,
        x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
    ) -> OrgContext:
        ctx = await _active_org_context(user, db, x_organization_id)
        if not any(ctx.can(p) for p in permissions):
            raise Forbidden()
        return ctx

    return dependency


async def _active_org_context(
    user: User, db: AsyncSession, organization_id: uuid.UUID | None
) -> OrgContext:
    if organization_id is None:
        memberships = await auth_service.active_memberships(db, user.id)
        if not memberships:
            raise NotFound("Organization")
        organization_id = memberships[0][1].id
    return await load_org_context(db, user, organization_id)


def active_org_permission(permission: Permission):
    """For routes without an org in the path (dashboard, trends, ...).

    Uses the X-Organization-Id header, falling back to the user's first
    organization.
    """

    async def dependency(
        user: CurrentUser,
        db: DB,
        x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
    ) -> OrgContext:
        ctx = await _active_org_context(user, db, x_organization_id)
        ctx.require(permission)
        return ctx

    return dependency
