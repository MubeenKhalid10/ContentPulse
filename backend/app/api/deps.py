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
from app.core.security import decode_local_token
from app.core.supabase import verify_supabase_token
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


async def _fused_org_context(
    request: Request, db: AsyncSession, settings: Settings, organization_id: uuid.UUID | None
) -> OrgContext | None:
    """The user, their membership and the organization in ONE query.

    Every organization route used to do these as two sequential queries; with a
    database that is far away each query is a visible delay. Returns None when
    the quick path doesn't apply (no organization header, first sight of a
    Supabase user, inactive user, not a member), so the regular path runs and
    raises the usual errors.
    """
    token = _extract_token(request, settings)
    if not token or organization_id is None:
        return None
    if settings.auth_provider == "local":
        try:
            who = User.id == uuid.UUID(decode_local_token(token, settings)["sub"])
        except ValueError:
            return None
    else:
        claims = await verify_supabase_token(token, settings)
        who = User.external_auth_id == str(claims["sub"])
    row = (
        await db.execute(
            select(User, OrganizationMember, Organization)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(
                who,
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
        )
    ).first()
    if row is None or not row[0].is_active:
        return None
    user, membership, organization = row
    return OrgContext(user=user, organization=organization, membership=membership)


async def _org_context_for_request(
    request: Request, db: AsyncSession, settings: Settings, organization_id: uuid.UUID | None
) -> OrgContext:
    ctx = await _fused_org_context(request, db, settings, organization_id)
    if ctx is not None:
        return ctx
    user = await get_current_user(await get_optional_user(request, db, settings))
    return await _active_org_context(user, db, organization_id)


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
        request: Request,
        db: DB,
        settings: AppSettings,
        x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
    ) -> OrgContext:
        ctx = await _org_context_for_request(request, db, settings, x_organization_id)
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
        request: Request,
        db: DB,
        settings: AppSettings,
        x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
    ) -> OrgContext:
        ctx = await _org_context_for_request(request, db, settings, x_organization_id)
        ctx.require(permission)
        return ctx

    return dependency
