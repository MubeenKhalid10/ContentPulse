import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
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
from app.models.enums import Platform, PostStatus, VersionSource


class Post(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "posts"

    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topic_candidates.id", ondelete="SET NULL"), index=True
    )
    content_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_strategies.id", ondelete="SET NULL")
    )
    platform: Mapped[Platform] = mapped_column(str_enum(Platform, "platform"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    # Status changes must go through app.services.workflow (spec §54, rule 5).
    status: Mapped[PostStatus] = mapped_column(
        str_enum(PostStatus, "post_status"),
        default=PostStatus.DRAFT,
        server_default=PostStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    current_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Variants are separate posts from the same strategy; all point at the
    # first post of their group so they can be compared side by side.
    variant_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = fk_user()


class PostVersion(UUIDPk, CreatedAt, OrgScoped, Base):
    """Immutable snapshot of post copy. Never updated in place (spec rule 4)."""

    __tablename__ = "post_versions"
    __table_args__ = (UniqueConstraint("post_id", "version_number"),)

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    hook: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[list[str]] = jsonb_list()
    mentions: Mapped[list[str]] = jsonb_list()
    meta: Mapped[dict] = jsonb_dict(name="metadata")
    source: Mapped[VersionSource] = mapped_column(
        str_enum(VersionSource, "version_source"), nullable=False
    )
    change_note: Mapped[str | None] = mapped_column(Text)
    ai_generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_generation_jobs.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = fk_user()
