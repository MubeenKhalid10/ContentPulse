import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.api.deps import DB, AppSettings, CurrentUser, OptionalUser
from app.core.config import Settings
from app.core.ratelimit import (
    INVITE_PER_IP,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    RESET_PER_ACCOUNT,
    RESET_PER_IP,
    limiter,
    per_ip,
)
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    AcceptInviteRequest,
    AuthConfig,
    InvitePreview,
    LoginRequest,
    MeResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(
    response: Response, token: str, expires_at: datetime, settings: Settings
) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        expires=expires_at,
        httponly=True,
        secure=settings.is_production if settings.cookie_secure is None else settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def _start_session(
    db: DB, user: User, response: Response, settings: Settings
) -> SessionResponse:
    token, expires_at = create_access_token(user.id, settings)
    _set_session_cookie(response, token, expires_at, settings)
    return SessionResponse(
        access_token=token,
        expires_at=expires_at,
        user=await auth_service.build_me(db, user),
    )


@router.get("/config", response_model=AuthConfig)
async def auth_config(settings: AppSettings) -> AuthConfig:
    if settings.auth_provider == "supabase":
        return AuthConfig(
            provider="supabase",
            password_reset=True,  # Supabase sends its own reset emails
            supabase_url=settings.supabase_url,
            supabase_anon_key=settings.supabase_anon_key,
        )
    return AuthConfig(provider="local", password_reset=settings.email_enabled)


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[per_ip(REGISTER_PER_IP)],
)
async def register(
    data: RegisterRequest, response: Response, db: DB, settings: AppSettings
) -> SessionResponse:
    user = await auth_service.register(db, data, settings)
    return await _start_session(db, user, response, settings)


@router.post("/login", response_model=SessionResponse, dependencies=[per_ip(LOGIN_PER_IP)])
async def login(
    data: LoginRequest, response: Response, db: DB, settings: AppSettings
) -> SessionResponse:
    # Per account too, so one address can't be guessed at from many IPs.
    await limiter.check(LOGIN_PER_ACCOUNT, data.email.lower())
    user = await auth_service.authenticate(db, data.email, data.password, settings)
    return await _start_session(db, user, response, settings)


@router.post(
    "/password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[per_ip(RESET_PER_IP)],
)
async def request_password_reset(
    data: PasswordResetRequest, db: DB, settings: AppSettings
) -> dict[str, str]:
    await limiter.check(RESET_PER_ACCOUNT, data.email.lower())
    await auth_service.request_password_reset(db, data.email, settings)
    # Same answer whether or not the account exists.
    return {"detail": "If an account exists for this email, a reset link is on its way."}


@router.post(
    "/password-reset/confirm",
    response_model=SessionResponse,
    dependencies=[per_ip(RESET_PER_IP)],
)
async def confirm_password_reset(
    data: PasswordResetConfirm, response: Response, db: DB, settings: AppSettings
) -> SessionResponse:
    user = await auth_service.reset_password(db, data.token, data.password, settings)
    return await _start_session(db, user, response, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=MeResponse)
async def me(
    user: CurrentUser,
    db: DB,
    x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
) -> MeResponse:
    return await auth_service.build_me(db, user, x_organization_id)


@router.get("/invites/{token}", response_model=InvitePreview)
async def preview_invite(token: str, db: DB) -> InvitePreview:
    return await auth_service.preview_invite(db, token)


@router.post("/invites/accept", response_model=MeResponse, dependencies=[per_ip(INVITE_PER_IP)])
async def accept_invite(
    data: AcceptInviteRequest,
    response: Response,
    db: DB,
    settings: AppSettings,
    current_user: OptionalUser,
) -> MeResponse:
    user = await auth_service.accept_invite(db, data, settings, current_user)
    if settings.auth_provider == "local":
        token, expires_at = create_access_token(user.id, settings)
        _set_session_cookie(response, token, expires_at, settings)
    me = await auth_service.build_me(db, user)
    return me
