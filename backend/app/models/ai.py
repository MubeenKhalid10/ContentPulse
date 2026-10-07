import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OrgScoped, UUIDPk, jsonb_dict, str_enum
from app.models.enums import JobStatus


class PromptTemplate(UUIDPk, CreatedAt, Base):
    """Versioned prompts so every generation can be traced (spec §59)."""

    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AIGenerationJob(UUIDPk, CreatedAt, OrgScoped, Base):
    __tablename__ = "ai_generation_jobs"

    type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="SET NULL")
    )
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"),
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict] = jsonb_dict()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LLMRequest(UUIDPk, CreatedAt, Base):
    """One row per model request the gateway made (or answered from cache).

    Metadata only: prompts and outputs are never stored here. `call_id` groups
    the attempts (retries, fallbacks) of one logical call; `job_id` links them
    to the AI job that asked.
    """

    __tablename__ = "llm_requests"
    __table_args__ = (Index("ix_llm_requests_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    workflow: Mapped[str] = mapped_column(String(60), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    # succeeded | failed | cached
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_kind: Mapped[str | None] = mapped_column(String(40))
    error_detail: Mapped[str | None] = mapped_column(String(300))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    queue_wait_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    usage_unavailable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
