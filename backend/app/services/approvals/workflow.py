"""Submitting a post for approval (spec §30-32). Shared by the design task
("Submit for approval") and the content studio ("Resubmit" after copy-only
changes), so every round records exactly what was reviewed."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransition
from app.models.approval import ApprovalComment, ApprovalRequest
from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import DesignBriefStatus, PostStatus
from app.models.post import Post
from app.models.user import User
from app.schemas.design import Person, ReviewComment, ReviewSummary
from app.services import audit
from app.services.audit import AuditAction
from app.services.workflow import transition_post

SUBMITTABLE = (PostStatus.DESIGN_UPLOADED, PostStatus.CHANGES_REQUESTED)


async def latest_creative_version(db: AsyncSession, post_id: uuid.UUID) -> int | None:
    return await db.scalar(
        select(func.max(CreativeAsset.version)).where(CreativeAsset.post_id == post_id)
    )


async def submit_post(
    db: AsyncSession, post: Post, user_id: uuid.UUID, note: str | None = None
) -> ApprovalRequest:
    """DESIGN_UPLOADED (or CHANGES_REQUESTED with a creative) → PENDING_APPROVAL,
    opening a new review round pinned to the current copy and creative."""
    creative = await latest_creative_version(db, post.id)
    if post.status not in SUBMITTABLE or creative is None:
        raise InvalidStateTransition(
            "Upload the creative before submitting it for approval."
            if creative is None
            else "This post isn't ready to be submitted for approval.",
            details={"from": post.status.value, "to": PostStatus.PENDING_APPROVAL.value},
        )
    if post.status == PostStatus.CHANGES_REQUESTED:
        await transition_post(db, post, PostStatus.DESIGN_UPLOADED, user_id=user_id)
    await transition_post(db, post, PostStatus.PENDING_APPROVAL, user_id=user_id)

    request = ApprovalRequest(
        organization_id=post.organization_id,
        post_id=post.id,
        post_version=post.current_version,
        creative_version=creative,
        submitted_by=user_id,
    )
    db.add(request)
    await db.flush()
    if note:
        db.add(
            ApprovalComment(
                organization_id=post.organization_id,
                approval_request_id=request.id,
                post_id=post.id,
                post_version=post.current_version,
                creative_version=creative,
                author_id=user_id,
                body=note,
                kind="resubmitted",
            )
        )
    brief = await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post.id, DesignBrief.status != DesignBriefStatus.CANCELLED)
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )
    if brief is not None:
        brief.status, brief.submitted_at = DesignBriefStatus.SUBMITTED, datetime.now(UTC)
    audit.record(
        db,
        organization_id=post.organization_id,
        user_id=user_id,
        action=AuditAction.APPROVAL_REQUESTED,
        entity_type="post",
        entity_id=post.id,
        new_value={
            "approval_request_id": request.id,
            "post_version": post.current_version,
            "creative_version": creative,
        },
    )
    return request


async def latest_review(db: AsyncSession, post_id: uuid.UUID) -> ReviewSummary | None:
    """The most recent approval round for a post, with its comments."""
    request = await db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.post_id == post_id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )
    if request is None:
        return None
    rounds = await db.scalar(select(func.count()).where(ApprovalRequest.post_id == post_id))
    comments = list(
        await db.scalars(
            select(ApprovalComment)
            .where(ApprovalComment.approval_request_id == request.id)
            .order_by(ApprovalComment.created_at)
        )
    )
    user_ids = {c.author_id for c in comments if c.author_id} | (
        {request.reviewer_id} if request.reviewer_id else set()
    )
    users = (
        {u.id: u for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )

    def person(user_id: uuid.UUID | None) -> Person | None:
        user = users.get(user_id) if user_id else None
        return Person(id=user.id, name=user.full_name, email=user.email) if user else None

    return ReviewSummary(
        request_id=request.id,
        status=request.status.value,
        round=rounds or 1,
        post_version=request.post_version,
        creative_version=request.creative_version,
        reviewer=person(request.reviewer_id),
        reviewed_at=request.reviewed_at,
        comments=[
            ReviewComment(
                body=c.body,
                kind=c.kind,
                author=person(c.author_id),
                post_version=c.post_version,
                creative_version=c.creative_version,
                created_at=c.created_at,
            )
            for c in comments
        ],
    )
