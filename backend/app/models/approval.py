import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, OrgScoped, UUIDPk, fk_user, str_enum
from app.models.enums import ApprovalStatus


class ApprovalRequest(UUIDPk, CreatedAt, OrgScoped, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        # One open review round per post, even when two reviewers or a double
        # click race.
        Index(
            "uq_approval_requests_one_pending",
            "post_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

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
    # What a change request opened: "copy", "design" or "both". NULL on anything
    # that isn't a design-stage change request (and on older ones: read as "both").
    scope: Mapped[str | None] = mapped_column(String(20))


class PostChangeRequest(UUIDPk, CreatedAt, OrgScoped, Base):
    """A creator asks an admin to reopen locked copy or a locked design."""

    __tablename__ = "post_change_requests"
    __table_args__ = (
        # One open request per post, so an admin answers it once.
        Index(
            "uq_post_change_requests_one_pending",
            "post_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # "copy", "design" or "both".
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # "pending", "accepted", "declined", or "closed" when the post moved on first.
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = fk_user()
    decided_by: Mapped[uuid.UUID | None] = fk_user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


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
