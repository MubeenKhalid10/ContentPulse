import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    OrgScoped,
    Timestamps,
    UUIDPk,
    fk_user,
    jsonb_dict,
    jsonb_list,
    str_enum,
)
from app.models.enums import Platform, RelevanceLevel, StrategyStatus, TopicStatus


class TopicCandidate(UUIDPk, Timestamps, OrgScoped, Base):
    """A trend that is worth considering for content (spec §19)."""

    __tablename__ = "topic_candidates"
    # One topic per trend; manual topics (trend_id NULL) are unconstrained.
    __table_args__ = (UniqueConstraint("organization_id", "trend_id"),)

    trend_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trends.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    relevance_level: Mapped[RelevanceLevel | None] = mapped_column(
        str_enum(RelevanceLevel, "relevance_level")
    )
    relevance_reason: Mapped[str | None] = mapped_column(Text)
    matched_services: Mapped[list[str]] = jsonb_list()
    # [{title, angle, platforms, evidence}] from the alignment analysis.
    suggested_angles: Mapped[list[dict]] = jsonb_list()
    target_audience: Mapped[str | None] = mapped_column(Text)
    recommended_platforms: Mapped[list[str]] = jsonb_list()
    # Explainable per-platform recommendation: [{platform, score, reasons, formats}].
    platform_fit: Mapped[list[dict]] = jsonb_list()
    # Claims the analysis found unsupported by the knowledge base.
    unsupported_claims: Mapped[list[str]] = jsonb_list()
    status: Mapped[TopicStatus] = mapped_column(
        str_enum(TopicStatus, "topic_status"),
        default=TopicStatus.NEW,
        server_default=TopicStatus.NEW.value,
        nullable=False,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = fk_user()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentStrategy(UUIDPk, Timestamps, OrgScoped, Base):
    """How a shortlisted topic becomes a post on one platform (spec §21)."""

    __tablename__ = "content_strategies"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topic_candidates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    platform: Mapped[Platform] = mapped_column(str_enum(Platform, "platform"), nullable=False)
    post_type: Mapped[str] = mapped_column(String(60), nullable=False)
    content_angle: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(String(120))
    target_audience: Mapped[str | None] = mapped_column(Text)
    hook_direction: Mapped[str | None] = mapped_column(Text)
    cta_direction: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(String(120))
    recommended_format: Mapped[str | None] = mapped_column(String(60))
    # Why this direction: from the AI suggestion or the rule-based draft.
    rationale: Mapped[str | None] = mapped_column(Text)
    # Platform-specific plan beyond the shared fields; Blog keeps its SEO plan
    # here (keywords, outline, meta direction). Empty for social platforms.
    details: Mapped[dict] = jsonb_dict()
    # "ai", "rules" or "manual": where the first draft came from.
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    status: Mapped[StrategyStatus] = mapped_column(
        str_enum(StrategyStatus, "strategy_status"),
        default=StrategyStatus.DRAFT,
        server_default=StrategyStatus.DRAFT.value,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = fk_user()
    approved_by: Mapped[uuid.UUID | None] = fk_user()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformRule(UUIDPk, Timestamps, OrgScoped, Base):
    """Per-organization platform playbook (spec §22): kept in the database, not
    in prompts. Seeded from app/services/topics/platform_defaults.py."""

    __tablename__ = "platform_rules"
    __table_args__ = (UniqueConstraint("organization_id", "platform"),)

    platform: Mapped[Platform] = mapped_column(str_enum(Platform, "platform"), nullable=False)
    # Post types offered for strategies, in order of preference.
    post_types: Mapped[list[str]] = jsonb_list()
    objectives: Mapped[list[str]] = jsonb_list()
    # Words in the audience, goals or topic that make this platform a good fit.
    affinity_keywords: Mapped[list[str]] = jsonb_list()
    tone: Mapped[str | None] = mapped_column(String(200))
    guidance: Mapped[str | None] = mapped_column(Text)
    max_length: Mapped[int | None] = mapped_column(Integer)
    hashtag_limit: Mapped[int | None] = mapped_column(Integer)
