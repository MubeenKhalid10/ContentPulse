import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OrgScoped, UUIDPk, fk_user, str_enum
from app.models.enums import ApprovalStatus


class ApprovalRequest(UUIDPk, CreatedAt, OrgScoped, Base):
    __tablename__ = "approval_requests"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Exactly what was reviewed: the copy version and creative version.
    post_version: Mapped[int] = mapped_column(Integer, nullable=False)
    creative_version: Mapped[int | None] = mapped_column(Integer)
    submitted_by: Mapped[uuid.UUID | None] = fk_user()
    reviewer_id: Mapped[uuid.UUID | None] = fk_user()
    status: Mapped[ApprovalStatus] = mapped_column(
        str_enum(ApprovalStatus, "approval_status"),
        default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    comments: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalComment(UUIDPk, CreatedAt, OrgScoped, Base):
    """Review comment pinned to the post version it refers to (spec §33)."""

    __tablename__ = "approval_comments"

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    post_version: Mapped[int] = mapped_column(Integer, nullable=False)
    creative_version: Mapped[int | None] = mapped_column(Integer)
    author_id: Mapped[uuid.UUID | None] = fk_user()
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "comment", or the decision it explains: "approved", "changes_requested",
    # "rejected", "resubmitted".
    kind: Mapped[str] = mapped_column(String(30), default="comment", server_default="comment")
