import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.email import send_email
from app.core.errors import AppError, Conflict, ErrorCode, Forbidden, NotFound, Unauthorized
from app.core.permissions import Role, permissions_for
from app.core.security import (
    create_password_reset_token,
    decode_local_token,
    hash_invite_token,
    hash_password,
    password_matches_fingerprint,
    read_password_reset_token,
    verify_password,
)
from app.core.supabase import verify_supabase_token
from app.models.enums import AuthProvider, MemberStatus
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.auth import (
    AcceptInviteRequest,
    InvitePreview,
    MembershipSummary,
    MeResponse,
    RegisterRequest,
)
from app.services import audit

# Verified against when the email is unknown, so response time does not reveal
# whether an account exists.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _require_local(settings: Settings) -> None:
    if settings.auth_provider != "local":
        raise Forbidden("Password sign-in is disabled. Sign in with your identity provider.")


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == normalize_email(email)))


async def register(db: AsyncSession, data: RegisterRequest, settings: Settings) -> User:
    _require_local(settings)
    email = normalize_email(data.email)
    existing = await get_user_by_email(db, email)
    if existing is not None and existing.password_hash is not None:
        raise Conflict("An account with this email already exists.")
    if existing is not None:
        # Placeholder account created by an invitation: they must accept the
        # invite link so we know they control the address.
        raise Conflict("This email has a pending invitation. Use the invite link to join.")

    user = User(
        email=email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        auth_provider=AuthProvider.LOCAL,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("An account with this email already exists.") from exc
    return user


async def authenticate(db: AsyncSession, email: str, password: str, settings: Settings) -> User:
    _require_local(settings)
    user = await get_user_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise Unauthorized("Invalid email or password.")
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise Unauthorized("Invalid email or password.")
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user


async def request_password_reset(db: AsyncSession, email: str, settings: Settings) -> None:
    """Email a reset link if the account exists. Says nothing either way."""
    _require_local(settings)
    user = await get_user_by_email(db, email)
    # Invited placeholders have no password yet; their invite link sets one.
    if user is None or user.password_hash is None or not user.is_active:
        return
    token = create_password_reset_token(user.id, user.password_hash, settings)
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    minutes = settings.password_reset_ttl_minutes
    await send_email(
        settings,
        to=user.email,
        subject="Reset your ContentPulse password",
        body=(
            f"Hi{' ' + user.full_name if user.full_name else ''},\n\n"
            "Someone asked to reset the password for this ContentPulse account.\n"
            f"Choose a new password here (the link works for {minutes} minutes, once):\n\n"
            f"{link}\n\n"
            "If it wasn't you, ignore this email; your password stays the same.\n"
        ),
    )


async def reset_password(db: AsyncSession, token: str, password: str, settings: Settings) -> User:
    _require_local(settings)
    user_id, fingerprint = read_password_reset_token(token, settings)
    user = await db.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or not password_matches_fingerprint(user.password_hash, fingerprint)
    ):
        raise Unauthorized("This reset link is invalid or has expired. Ask for a new one.")
    user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user


async def user_from_token(db: AsyncSession, token: str, settings: Settings) -> User:
    if settings.auth_provider == "local":
        claims = decode_local_token(token, settings)
        try:
            user = await db.get(User, uuid.UUID(claims["sub"]))
        except ValueError as exc:
            raise Unauthorized("Invalid authentication token.") from exc
    else:
        claims = await verify_supabase_token(token, settings)
        user = await _resolve_supabase_user(db, claims)

    if user is None or not user.is_active:
        raise Unauthorized("Account not found or disabled.")
    return user


async def _resolve_supabase_user(db: AsyncSession, claims: dict) -> User:
    """Link a Supabase identity to a platform user, provisioning on first sight."""
    subject = str(claims["sub"])
    user = await db.scalar(select(User).where(User.external_auth_id == subject))
    if user is not None:
        return user

    email = claims.get("email")
    if not email:
        raise Unauthorized("Identity token has no email claim.")
    user = await get_user_by_email(db, email)
    if user is None:
        user = User(email=normalize_email(email), auth_provider=AuthProvider.SUPABASE)
        db.add(user)
    user.external_auth_id = subject
    user.auth_provider = AuthProvider.SUPABASE
    if not user.full_name:
        metadata = claims.get("user_metadata") or {}
        user.full_name = metadata.get("full_name") or metadata.get("name")
    user.last_login_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError:
        # Two first requests from a new user raced; the other one created it.
        await db.rollback()
        user = await db.scalar(select(User).where(User.external_auth_id == subject))
        if user is None:
            raise
    return user


async def active_memberships(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[OrganizationMember, Organization]]:
    rows = await db.execute(
        select(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == MemberStatus.ACTIVE,
        )
        .order_by(OrganizationMember.created_at)
    )
    return [(m, o) for m, o in rows]


async def build_me(
    db: AsyncSession, user: User, requested_org_id: uuid.UUID | None = None
) -> MeResponse:
    memberships = await active_memberships(db, user.id)
    active = next(
        ((m, o) for m, o in memberships if o.id == requested_org_id),
        memberships[0] if memberships else None,
    )
    role: Role | None = active[0].role if active else None
    return MeResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        organization_id=active[1].id if active else None,
        role=role,
        permissions=permissions_for(role) if role else [],
        memberships=[
            MembershipSummary(
                organization_id=o.id,
                organization_name=o.name,
                organization_slug=o.slug,
                role=m.role,
            )
            for m, o in memberships
        ],
    )


async def _pending_invite(
    db: AsyncSession, raw_token: str
) -> tuple[OrganizationMember, Organization, User]:
    row = (
        await db.execute(
            select(OrganizationMember, Organization, User)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.invite_token_hash == hash_invite_token(raw_token),
                OrganizationMember.status == MemberStatus.INVITED,
            )
            .with_for_update(of=OrganizationMember)
        )
    ).first()
    if row is None:
        raise NotFound("Invitation")
    member, org, user = row
    if member.invite_expires_at is None or member.invite_expires_at < datetime.now(UTC):
        raise AppError(ErrorCode.VALIDATION_ERROR, "This invitation has expired.", status_code=410)
    return member, org, user


async def preview_invite(db: AsyncSession, raw_token: str) -> InvitePreview:
    member, org, user = await _pending_invite(db, raw_token)
    return InvitePreview(
        organization_name=org.name,
        email=user.email,
        role=member.role,
        has_account=user.password_hash is not None or user.external_auth_id is not None,
        expires_at=member.invite_expires_at,
    )


async def accept_invite(
    db: AsyncSession,
    data: AcceptInviteRequest,
    settings: Settings,
    current_user: User | None,
) -> User:
    member, org, user = await _pending_invite(db, data.token)

    if settings.auth_provider == "supabase":
        # Identity is proven by the Supabase session, which must match the invitee.
        if current_user is None or current_user.id != user.id:
            raise Forbidden("Sign in as the invited email address to accept this invitation.")
    elif user.password_hash is None:
        if data.password is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Choose a password to finish joining.")
        user.password_hash = hash_password(data.password)
    elif data.password is None or not verify_password(data.password, user.password_hash):
        # Existing account: holding the link alone must not grant a session.
        raise Unauthorized("Enter your current password to accept this invitation.")

    if not user.full_name:
        user.full_name = data.full_name
    now = datetime.now(UTC)
    user.last_login_at = now
    member.status = MemberStatus.ACTIVE
    member.joined_at = now
    member.invite_token_hash = None
    member.invite_expires_at = None
    audit.record(
        db,
        organization_id=org.id,
        user_id=user.id,
        action=audit.AuditAction.MEMBER_JOINED,
        entity_type="organization_member",
        entity_id=member.id,
        new_value={"email": user.email, "role": member.role},
    )
    await db.commit()
    return user
