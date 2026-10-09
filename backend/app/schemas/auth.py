import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, StringConstraints

from app.core.permissions import Role
from app.schemas.common import Name

Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    full_name: Name


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class AcceptInviteRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=10, max_length=200)]
    full_name: Name
    # Required only when the invited user does not have a password yet.
    password: Password | None = None


class MembershipSummary(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    role: Role


class MeResponse(BaseModel):
    """GET /auth/me — shape follows spec §35, plus memberships and permissions."""

    id: uuid.UUID
    name: str | None
    email: str
    organization_id: uuid.UUID | None
    role: Role | None
    permissions: list[str]
    memberships: list[MembershipSummary]


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: MeResponse


class AuthConfig(BaseModel):
    """Public: tells the web app how users sign in."""

    provider: Literal["local", "supabase"]
    # Local mode: true when the server can email reset links (SMTP is set up).
    password_reset: bool = False
    supabase_url: str | None = None
    # The anon/publishable key is designed to be public (row-level security
    # protects data); never the service-role key.
    supabase_anon_key: str | None = None


class InvitePreview(BaseModel):
    organization_name: str
    email: str
    role: Role
    has_account: bool
    expires_at: datetime


class PasswordResetRequest(BaseModel):
    email: EmailStr


class ProfileUpdate(BaseModel):
    """The signed-in user's own details (Settings > Your profile)."""

    full_name: Name


class PasswordChange(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class PasswordResetConfirm(BaseModel):
    token: Annotated[str, StringConstraints(min_length=20, max_length=2000)]
    password: Password
