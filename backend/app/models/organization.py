import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    CreatedAt,
    OrgScoped,
    Timestamps,
    UUIDPk,
    fk_user,
    jsonb_list,
    str_enum,
)
from app.models.enums import MemberStatus, OfferingKind, Role, TrendFrequency
from app.models.user import User


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(120))
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")


class OrganizationSettings(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "organization_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    default_language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    default_timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    target_markets: Mapped[list[str]] = jsonb_list()
    target_audience: Mapped[str | None] = mapped_column(Text)
    content_goals: Mapped[list[str]] = jsonb_list()
    enabled_platforms: Mapped[list[str]] = jsonb_list()
    enabled_sources: Mapped[list[str]] = jsonb_list()
    tracked_keywords: Mapped[list[str]] = jsonb_list()
    # Extra inputs for trend sources: subreddit names and RSS/Atom feed URLs.
    subreddits: Mapped[list[str]] = jsonb_list()
    rss_feeds: Mapped[list[str]] = jsonb_list()
    trend_frequency: Mapped[TrendFrequency] = mapped_column(
        str_enum(TrendFrequency, "trend_frequency"),
        default=TrendFrequency.DAILY,
        server_default=TrendFrequency.DAILY.value,
        nullable=False,
    )


class BrandProfile(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (UniqueConstraint("organization_id"),)

    brand_voice: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(Text)
    writing_style: Mapped[str | None] = mapped_column(Text)
    preferred_terms: Mapped[list[str]] = jsonb_list()
    forbidden_terms: Mapped[list[str]] = jsonb_list()
    content_guidelines: Mapped[str | None] = mapped_column(Text)
    cta_guidelines: Mapped[str | None] = mapped_column(Text)
    hashtag_guidelines: Mapped[str | None] = mapped_column(Text)
    # Visual identity, surfaced to designers in design briefs.
    brand_colors: Mapped[list[str]] = jsonb_list()
    typography: Mapped[str | None] = mapped_column(Text)


class OrganizationService(UUIDPk, CreatedAt, OrgScoped, Base):
    """Services, products and areas of expertise the organization offers."""

    __tablename__ = "organization_services"

    kind: Mapped[OfferingKind] = mapped_column(
        str_enum(OfferingKind, "offering_kind"),
        default=OfferingKind.SERVICE,
        server_default=OfferingKind.SERVICE.value,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class OrganizationMember(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[Role] = mapped_column(str_enum(Role, "member_role"), nullable=False)
    status: Mapped[MemberStatus] = mapped_column(
        str_enum(MemberStatus, "member_status"),
        default=MemberStatus.ACTIVE,
        server_default=MemberStatus.ACTIVE.value,
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID | None] = fk_user()
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
