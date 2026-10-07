import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
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
from app.models.enums import DesignBriefStatus


class DesignBrief(UUIDPk, Timestamps, OrgScoped, Base):
    """Design direction for a post; doubles as the designer's task (spec §27, §41)."""

    __tablename__ = "design_briefs"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    format: Mapped[str] = mapped_column(String(60), nullable=False)
    dimensions: Mapped[str | None] = mapped_column(String(40))
    visual_concept: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    supporting_text: Mapped[str | None] = mapped_column(Text)
    slide_structure: Mapped[list] = jsonb_list()
    visual_elements: Mapped[list] = jsonb_list()
    brand_requirements: Mapped[dict] = jsonb_dict()
    cta: Mapped[str | None] = mapped_column(Text)
    designer_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DesignBriefStatus] = mapped_column(
        str_enum(DesignBriefStatus, "design_brief_status"),
        default=DesignBriefStatus.OPEN,
        server_default=DesignBriefStatus.OPEN.value,
        nullable=False,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = fk_user(index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "rules" (built from the post), "ai" (written by the LLM) or "edited" (a
    # person changed it; the AI never overwrites an edited brief).
    source: Mapped[str] = mapped_column(String(20), default="rules", server_default="rules")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreativeAsset(UUIDPk, CreatedAt, OrgScoped, Base):
    """Designer-uploaded file. Bytes live in S3; only metadata here (spec §29)."""

    __tablename__ = "creative_assets"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    design_brief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("design_briefs.id", ondelete="SET NULL")
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_url: Mapped[str | None] = mapped_column(String(2048))
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048))
    # Creative revision number; several files (e.g. carousel slides) share a version.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The designer's note for this creative version (same on every file of it).
    note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = fk_user()
