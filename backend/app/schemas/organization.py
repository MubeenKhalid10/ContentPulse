import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.core.permissions import Role
from app.models.enums import MemberStatus, OfferingKind, Platform, TrendFrequency
from app.schemas.common import (
    HttpUrlStr,
    LogoPosition,
    LongText,
    Name,
    ORMModel,
    PatchModel,
    Tag,
    TagList,
    Timezone,
)


def _known_sources(keys: list[str]) -> list[str]:
    from app.sources import SOURCES

    unknown = [k for k in keys if k not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    return list(dict.fromkeys(keys))


SourceKeys = Annotated[list[Tag], AfterValidator(_known_sources)]
Subreddit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^(r/)?[A-Za-z0-9_]{2,21}$"),
    AfterValidator(lambda v: v.removeprefix("r/")),
]


# --- Organization -----------------------------------------------------------
class OrganizationCreate(BaseModel):
    name: Name
    website_url: HttpUrlStr | None = None
    description: LongText | None = None
    industry: Tag | None = None
    timezone: Timezone = "UTC"


class OrganizationUpdate(PatchModel):
    non_nullable = frozenset({"name", "timezone"})

    name: Name | None = None
    website_url: HttpUrlStr | None = None
    description: LongText | None = None
    industry: Tag | None = None
    logo_url: HttpUrlStr | None = None
    timezone: Timezone | None = None


class OrganizationRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    website_url: str | None
    description: str | None
    industry: str | None
    logo_url: str | None
    # An uploaded logo exists (shown at /organizations/{id}/logo); it wins over logo_url.
    has_logo_file: bool = False
    timezone: str
    created_at: datetime
    updated_at: datetime


# --- Settings ---------------------------------------------------------------
class SettingsUpdate(PatchModel):
    non_nullable = frozenset(
        {
            "default_language",
            "default_timezone",
            "target_markets",
            "content_goals",
            "enabled_platforms",
            "enabled_sources",
            "tracked_keywords",
            "subreddits",
            "rss_feeds",
            "trend_frequency",
        }
    )

    default_language: Tag | None = None
    default_timezone: Timezone | None = None
    target_markets: TagList | None = None
    target_audience: LongText | None = None
    content_goals: TagList | None = None
    enabled_platforms: list[Platform] | None = None
    enabled_sources: SourceKeys | None = None
    tracked_keywords: TagList | None = None
    subreddits: Annotated[list[Subreddit], Field(max_length=30)] | None = None
    rss_feeds: Annotated[list[HttpUrlStr], Field(max_length=30)] | None = None
    trend_frequency: TrendFrequency | None = None


class SettingsRead(ORMModel):
    default_language: str
    default_timezone: str
    target_markets: list[str]
    target_audience: str | None
    content_goals: list[str]
    enabled_platforms: list[Platform]
    enabled_sources: list[str]
    tracked_keywords: list[str]
    subreddits: list[str]
    rss_feeds: list[str]
    trend_frequency: TrendFrequency
    updated_at: datetime


# --- Brand ------------------------------------------------------------------
class BrandUpdate(PatchModel):
    non_nullable = frozenset(
        {"preferred_terms", "forbidden_terms", "brand_colors", "logo_position"}
    )

    brand_voice: LongText | None = None
    tone: LongText | None = None
    writing_style: LongText | None = None
    preferred_terms: TagList | None = None
    forbidden_terms: TagList | None = None
    content_guidelines: LongText | None = None
    cta_guidelines: LongText | None = None
    hashtag_guidelines: LongText | None = None
    brand_colors: TagList | None = None
    typography: LongText | None = None
    logo_position: LogoPosition | None = None


class BrandRead(ORMModel):
    brand_voice: str | None
    tone: str | None
    writing_style: str | None
    preferred_terms: list[str]
    forbidden_terms: list[str]
    content_guidelines: str | None
    cta_guidelines: str | None
    hashtag_guidelines: str | None
    brand_colors: list[str]
    typography: str | None
    logo_position: LogoPosition
    updated_at: datetime


# --- Services / products / expertise ----------------------------------------
class ServiceCreate(BaseModel):
    kind: OfferingKind = OfferingKind.SERVICE
    name: Name
    description: LongText | None = None
    category: Tag | None = None
    active: bool = True


class ServiceUpdate(PatchModel):
    non_nullable = frozenset({"kind", "name", "active"})

    kind: OfferingKind | None = None
    name: Name | None = None
    description: LongText | None = None
    category: Tag | None = None
    active: bool | None = None


class ServiceRead(ORMModel):
    id: uuid.UUID
    kind: OfferingKind
    name: str
    description: str | None
    category: str | None
    active: bool
    created_at: datetime


# --- Team -------------------------------------------------------------------
class MemberRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: Role
    status: MemberStatus
    joined_at: datetime | None
    invite_expires_at: datetime | None
    created_at: datetime


class InviteCreate(BaseModel):
    email: EmailStr
    role: Role


class InviteResponse(BaseModel):
    member: MemberRead
    # Returned once; only its hash is stored. Shown to the admin to share
    # when it could not be emailed.
    invite_url: str
    # True when the invitation was emailed (SMTP configured and accepted).
    email_sent: bool = False


class MemberUpdate(PatchModel):
    non_nullable = frozenset({"role", "status"})

    role: Role | None = None
    status: MemberStatus | None = None


# --- Audit ------------------------------------------------------------------
class AuditLogRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None = None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    old_value: dict | None
    new_value: dict | None
    created_at: datetime
