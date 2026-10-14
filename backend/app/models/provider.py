"""Platform-wide provider state, shared by all organizations.

Backend-only tables: no organization profiles, queries in clear text,
provider content tied to an organization, or credentials are stored here, and
no API endpoint returns their rows. The only organization reference is the
usage ledger's per-organization request counters (fair-share budgets).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProviderCache(Base):
    """Shared provider responses (the persistent level of the source cache).

    `key` is a SHA-256 of the canonical request (app/sources/cache_policy.py):
    it identifies what was asked, never who asked, and contains no secrets. A
    row without `body` is a lease: one worker is fetching that response.
    """

    __tablename__ = "provider_cache"
    __table_args__ = (Index("ix_provider_cache_expires_at", "expires_at"),)

    key: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    content_type: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[bytes | None] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProviderUsage(Base):
    """Outbound requests per provider and UTC day (cache hits are not counted).

    `scope` is "*" for the provider-wide total, or an organization id for that
    organization's share (fair-share budgets). Reservations are atomic, so
    concurrent workers can't overshoot a configured budget.
    """

    __tablename__ = "provider_usage"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    scope: Mapped[str] = mapped_column(String(40), primary_key=True)
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Requests the budget allowed in monitor mode although it was exceeded.
    over_budget: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InstagramHashtagUse(Base):
    """Hashtags searched per Instagram account in a rolling 7-day window
    (Instagram allows 30 unique hashtags per account per 7 days, shared by
    every organization using the platform's account)."""

    __tablename__ = "instagram_hashtag_usage"

    # SHA-256 prefix of the Instagram account id (not the id itself).
    account: Mapped[str] = mapped_column(String(16), primary_key=True)
    hashtag: Mapped[str] = mapped_column(String(100), primary_key=True)
    first_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
