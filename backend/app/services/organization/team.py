import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.email import send_email
from app.core.errors import AppError, Conflict, ErrorCode, NotFound
from app.core.permissions import Role
from app.core.security import generate_invite_token
from app.models.enums import AuthProvider, MemberStatus
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.organization import InviteCreate, InviteResponse, MemberRead, MemberUpdate
from app.services import audit
from app.services.audit import AuditAction
from app.services.auth import get_user_by_email, normalize_email


def to_read(member: OrganizationMember) -> MemberRead:
    return MemberRead(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
        invite_expires_at=member.invite_expires_at,
        created_at=member.created_at,
    )


async def list_members(db: AsyncSession, organization_id: uuid.UUID) -> list[MemberRead]:
    rows = await db.scalars(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.created_at)
    )
    return [to_read(m) for m in rows]


async def get_member(
    db: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID, *, lock: bool = False
) -> OrganizationMember:
    query = select(OrganizationMember).where(
        OrganizationMember.id == member_id,
        OrganizationMember.organization_id == organization_id,
    )
    if lock:
        query = query.with_for_update(of=OrganizationMember)
    member = await db.scalar(query)
    if member is None:
        raise NotFound("Member")
    return member


async def invite_member(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    inviter_id: uuid.UUID,
    data: InviteCreate,
    settings: Settings,
) -> InviteResponse:
    email = normalize_email(data.email)
    user = await get_user_by_email(db, email)
    if user is None:
        provider = (
            AuthProvider.SUPABASE if settings.auth_provider == "supabase" else AuthProvider.LOCAL
        )
        user = User(email=email, auth_provider=provider)
        db.add(user)
        await db.flush()

    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if member is not None and member.status == MemberStatus.ACTIVE:
        raise Conflict(f"{email} is already a member of this organization.")
    if member is not None and member.status == MemberStatus.DISABLED:
        raise Conflict(f"{email} is a disabled member. Re-enable them instead of inviting.")

    raw_token, token_hash = generate_invite_token()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.invite_ttl_hours)
    if member is None:
        member = OrganizationMember(organization_id=organization_id, user_id=user.id)
        db.add(member)
    # A repeat invite replaces the previous token (and role).
    member.role = data.role
    member.status = MemberStatus.INVITED
    member.invited_by = inviter_id
    member.invite_token_hash = token_hash
    member.invite_expires_at = expires_at
    await db.flush()

    audit.record(
        db,
        organization_id=organization_id,
        user_id=inviter_id,
        action=AuditAction.MEMBER_INVITED,
        entity_type="organization_member",
        entity_id=member.id,
        new_value={"email": email, "role": data.role},
    )
    await db.commit()
    await db.refresh(member, attribute_names=["user"])
    invite_url = f"{settings.frontend_url.rstrip('/')}/invite/{raw_token}"
    organization = await db.get(Organization, organization_id)
    org_name = organization.name if organization else "a ContentPulse organization"
    email_sent = await send_email(
        settings,
        to=email,
        subject=f"You're invited to {org_name} on ContentPulse",
        body=(
            f"You've been invited to join {org_name} on ContentPulse "
            f"with the {Role(data.role).value.capitalize()} role.\n\n"
            "Accept the invitation here "
            f"(the link works for {settings.invite_ttl_hours} hours):\n\n"
            f"{invite_url}\n\n"
            "If you weren't expecting this, you can ignore this email.\n"
        ),
    )
    return InviteResponse(member=to_read(member), invite_url=invite_url, email_sent=email_sent)


async def _ensure_admin_remains(
    db: AsyncSession, organization_id: uuid.UUID, losing_admin: OrganizationMember
) -> None:
    """Refuse changes that would leave the organization without an active admin."""
    # Lock admin rows so two concurrent demotions cannot both pass the check.
    admin_ids = (
        await db.scalars(
            select(OrganizationMember.id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == Role.ADMIN,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
            .with_for_update()
        )
    ).all()
    if set(admin_ids) <= {losing_admin.id}:
        raise Conflict("An organization must keep at least one active admin.")


def _is_active_admin(member: OrganizationMember) -> bool:
    return member.role == Role.ADMIN and member.status == MemberStatus.ACTIVE


async def update_member(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    member_id: uuid.UUID,
    data: MemberUpdate,
) -> MemberRead:
    member = await get_member(db, organization_id, member_id, lock=True)
    changes = data.changes()

    if changes.get("status") == MemberStatus.INVITED:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Use an invitation to set a member to invited.")
    if member.status == MemberStatus.INVITED and changes.get("status") == MemberStatus.ACTIVE:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invited members become active by accepting.")

    loses_admin = _is_active_admin(member) and (
        changes.get("role", member.role) != Role.ADMIN
        or changes.get("status", member.status) != MemberStatus.ACTIVE
    )
    if loses_admin:
        await _ensure_admin_remains(db, organization_id, member)

    old, new = audit.diff(member, changes)
    if new:
        for field, value in changes.items():
            setattr(member, field, value)
        audit.record(
            db,
            organization_id=organization_id,
            user_id=actor_id,
            action=AuditAction.MEMBER_UPDATED,
            entity_type="organization_member",
            entity_id=member.id,
            old_value=old,
            new_value=new,
        )
        await db.commit()
        await db.refresh(member)
    return to_read(member)


async def remove_member(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    member = await get_member(db, organization_id, member_id, lock=True)
    if _is_active_admin(member):
        await _ensure_admin_remains(db, organization_id, member)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=actor_id,
        action=AuditAction.MEMBER_REMOVED,
        entity_type="organization_member",
        entity_id=member.id,
        old_value={"email": member.user.email, "role": member.role, "status": member.status},
    )
    await db.delete(member)
    await db.commit()
