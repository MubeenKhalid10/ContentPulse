import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAt,
    OrgScoped,
    Timestamps,
    UUIDPk,
    fk_user,
    jsonb_dict,
    jsonb_list,
    str_enum,
)
from app.models.enums import (
    DiscoveryRunStatus,
    RelevanceLevel,
    RunTrigger,
    SourceHealth,
    TrendStatus,
)


class TrendSource(UUIDPk, Timestamps, Base):
    """Platform-wide registry and health of trend source adapters (spec §60)."""

    __tablename__ = "trend_sources"

    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")
    health: Mapped[SourceHealth] = mapped_column(
        str_enum(SourceHealth, "source_health"),
        default=SourceHealth.UNKNOWN,
        server_default=SourceHealth.UNKNOWN.value,
        nullable=False,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    rate_limit: Mapped[dict] = jsonb_dict()
    config: Mapped[dict] = jsonb_dict()


class Trend(UUIDPk, Timestamps, OrgScoped, Base):
    """Canonical, deduplicated trend (spec §12). Mentions hang off it."""

    __tablename__ = "trends"
    __table_args__ = (
        UniqueConstraint("organization_id", "canonical_key"),
        Index("ix_trends_org_last_seen", "organization_id", "last_seen_at"),
    )

    canonical_key: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = jsonb_list()
    category: Mapped[str | None] = mapped_column(String(120))
    locations: Mapped[list[str]] = jsonb_list()
    sources: Mapped[list[str]] = jsonb_list()
    status: Mapped[TrendStatus] = mapped_column(
        str_enum(TrendStatus, "trend_status"),
        default=TrendStatus.NEW,
        server_default=TrendStatus.NEW.value,
        nullable=False,
        index=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Individual scoring signals (0-100), exposed in the UI (spec §13).
    signals: Mapped[dict] = jsonb_dict()
    opportunity_score: Mapped[float | None] = mapped_column(Float, index=True)

    # Organization alignment result (spec §15). Human-overridable.
    relevance_level: Mapped[RelevanceLevel | None] = mapped_column(
        str_enum(RelevanceLevel, "relevance_level"), index=True
    )
    relevance_confidence: Mapped[float | None] = mapped_column(Float)
    relevance_overridden: Mapped[bool] = mapped_column(default=False, server_default="false")
    alignment: Mapped[dict] = jsonb_dict()
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrendMention(UUIDPk, OrgScoped, Base):
    """One observation of a trend from one source (spec §11)."""

    __tablename__ = "trend_mentions"
    __table_args__ = (UniqueConstraint("organization_id", "source", "source_item_id"),)

    trend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trends.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(500), nullable=False)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = jsonb_list()
    category: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Updated each time a later run sees the same item again.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engagement: Mapped[int | None] = mapped_column(BigInteger)
    # Human-readable engagement, e.g. "200K+ searches" or "1,258 points".
    engagement_label: Mapped[str | None] = mapped_column(String(120))
    growth_indicator: Mapped[float | None] = mapped_column(Float)
    raw_data: Mapped[dict] = jsonb_dict()


class TrendDiscoveryRun(UUIDPk, CreatedAt, OrgScoped, Base):
    """One trend collection run across sources (spec §14, §46)."""

    __tablename__ = "trend_discovery_runs"
    __table_args__ = (
        Index("ix_trend_discovery_runs_org_created", "organization_id", "created_at"),
    )

    status: Mapped[DiscoveryRunStatus] = mapped_column(
        str_enum(DiscoveryRunStatus, "discovery_run_status"),
        default=DiscoveryRunStatus.QUEUED,
        server_default=DiscoveryRunStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    trigger: Mapped[RunTrigger] = mapped_column(str_enum(RunTrigger, "run_trigger"), nullable=False)
    sources: Mapped[list[str]] = jsonb_list()
    locations: Mapped[list[str]] = jsonb_list()
    # Per-source outcome: {key: {status, items, error, mode, duration_ms}}
    results: Mapped[dict] = jsonb_dict()
    warnings: Mapped[list[str]] = jsonb_list()
    items_collected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trends_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trends_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mentions_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = fk_user()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
