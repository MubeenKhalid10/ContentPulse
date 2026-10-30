"""A creator asks an admin to reopen locked work.

Locked copy and designs stay locked until an admin agrees. Accepting does what
the admin's own "Request changes" does, on whichever round is current: it decides
a round still waiting for review, or reopens an approved one.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.errors import Conflict, InvalidStateTransition, NotFound, require
from app.models.approval import ApprovalRequest, PostChangeRequest
from app.models.enums import ApprovalStatus
from app.models.post import Post
from app.models.topic import TopicCandidate
from app.schemas.approval import (
    ApprovalPost,
    ChangeRequestItem,
    ChangeRequestPage,
    CommentRead,
)
from app.schemas.design import ChangeRequestRead
from app.services import audit
from app.services.approvals import service, workflow
from app.services.audit import AuditAction


async def _lock_post(db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    post = await db.scalar(
        select(Post)
        .where(Post.id == post_id, Post.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if post is None:
        raise NotFound("Post")
    return post


async def _read(db: AsyncSession, request: PostChangeRequest) -> ChangeRequestRead:
    return (await workflow.change_request_reads(db, [request]))[request.id]


def _record(
    db: AsyncSession, request: PostChangeRequest, user_id: uuid.UUID, action: AuditAction
) -> None:
    audit.record(
        db,
        organization_id=request.organization_id,
        user_id=user_id,
        action=action,
        entity_type="post",
        entity_id=request.post_id,
        new_value={"change_request_id": request.id, "scope": request.scope},
    )


async def create(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    scope: str,
    note: str,
) -> ChangeRequestRead:
    post = await _lock_post(db, organization_id, post_id)
    if scope not in await workflow.change_request_scopes(db, post):
        raise InvalidStateTransition(
            "This can't be requested at the post's current step.",
            details={"status": post.status.value, "scope": scope},
        )
    waiting = await db.scalar(
        select(PostChangeRequest.id).where(
            PostChangeRequest.post_id == post.id, PostChangeRequest.status == "pending"
        )
    )
    if waiting:
        raise Conflict("A change request for this post is already waiting for an admin.")
    request = PostChangeRequest(
        organization_id=organization_id,
        post_id=post.id,
        scope=scope,
        note=note,
        requested_by=user_id,
    )
    db.add(request)
    await db.flush()
    _record(db, request, user_id, AuditAction.CHANGE_REQUEST_CREATED)
    await db.commit()
    return await _read(db, request)


async def _pending(
    db: AsyncSession, organization_id: uuid.UUID, request_id: uuid.UUID
) -> PostChangeRequest:
    """The request, freshly read with its post locked, still waiting for a decision."""
    found = await db.scalar(
        select(PostChangeRequest).where(
            PostChangeRequest.id == request_id,
            PostChangeRequest.organization_id == organization_id,
        )
    )
    if found is None:
        raise NotFound("Change request")
    await _lock_post(db, organization_id, found.post_id)
    request = require(
        await db.scalar(
            select(PostChangeRequest)
            .where(PostChangeRequest.id == request_id)
            .execution_options(populate_existing=True)
        ),
        "change request",
    )
    if request.status != "pending":
        raise InvalidStateTransition("This change request was already decided.")
    return request


async def accept(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, request_id: uuid.UUID
) -> ChangeRequestRead:
    request = await _pending(db, organization_id, request_id)
    post = require(await db.get(Post, request.post_id), "post")
    if request.scope not in await workflow.change_request_scopes(db, post):
        raise InvalidStateTransition(
            "The post has moved on, so this request no longer applies. Decline it instead.",
            details={"status": post.status.value},
        )
    latest = require(
        await db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.post_id == post.id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        ),
        "approval",
    )
    # Before the post moves, or moving it would close this request as out of date.
    request.status, request.decided_by, request.decided_at = "accepted", user_id, utcnow()
    _record(db, request, user_id, AuditAction.CHANGE_REQUEST_ACCEPTED)
    await db.flush()
    comment = f"Creator's change request: {request.note}"
    # Both commit, together with the request's new status.
    if latest.status == ApprovalStatus.PENDING:
        await service.decide(
            db,
            organization_id,
            user_id,
            latest.id,
            ApprovalStatus.CHANGES_REQUESTED,
            comment,
            request.scope,
        )
    else:
        await service.reopen(db, organization_id, user_id, latest.id, comment, request.scope)
    return await _read(db, request)


async def decline(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: uuid.UUID,
    note: str | None,
) -> ChangeRequestRead:
    request = await _pending(db, organization_id, request_id)
    request.status, request.decided_by, request.decided_at = "declined", user_id, utcnow()
    request.decision_note = note
    _record(db, request, user_id, AuditAction.CHANGE_REQUEST_DECLINED)
    await db.commit()
    return await _read(db, request)


async def list_pending(
    db: AsyncSession, organization_id: uuid.UUID, *, limit: int, offset: int
) -> ChangeRequestPage:
    """The queue on Approvals, oldest first."""
    filters = (
        PostChangeRequest.organization_id == organization_id,
        PostChangeRequest.status == "pending",
    )
    total = await db.scalar(select(func.count()).select_from(PostChangeRequest).where(*filters))
    rows = list(
        await db.scalars(
            select(PostChangeRequest)
            .where(*filters)
            .order_by(PostChangeRequest.created_at)
            .limit(limit)
            .offset(offset)
        )
    )
    reads = await workflow.change_request_reads(db, rows)
    post_ids = {r.post_id for r in rows}
    posts = (
        {p.id: p for p in await db.scalars(select(Post).where(Post.id.in_(post_ids)))}
        if post_ids
        else {}
    )
    topic_ids = {p.topic_id for p in posts.values() if p.topic_id}
    topics = (
        dict(
            (
                await db.execute(
                    select(TopicCandidate.id, TopicCandidate.title).where(
                        TopicCandidate.id.in_(topic_ids)
                    )
                )
            ).all()
        )
        if topic_ids
        else {}
    )
    return ChangeRequestPage(
        items=[
            ChangeRequestItem(
                **reads[r.id].model_dump(),
                post=ApprovalPost(
                    id=posts[r.post_id].id,
                    title=posts[r.post_id].title,
                    platform=posts[r.post_id].platform,
                    status=posts[r.post_id].status,
                    current_version=posts[r.post_id].current_version,
                ),
                topic_title=topics.get(posts[r.post_id].topic_id),
            )
            for r in rows
        ],
        total=total or 0,
    )


async def post_comments(
    db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID
) -> list[CommentRead]:
    """The review conversation, for people who work on the post but don't review it."""
    post = await db.scalar(
        select(Post.id).where(Post.id == post_id, Post.organization_id == organization_id)
    )
    if post is None:
        raise NotFound("Post")
    return await service.comments(db, post_id)


async def add_post_comment(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, post_id: uuid.UUID, body: str
) -> list[CommentRead]:
    """A comment on the post's latest review round."""
    latest = await db.scalar(
        select(ApprovalRequest.id)
        .where(ApprovalRequest.post_id == post_id, ApprovalRequest.organization_id == organization_id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )
    if latest is None:
        raise InvalidStateTransition("This post hasn't been sent for review yet.")
    await service.add_comment(db, organization_id, user_id, latest, body)
    return await service.comments(db, post_id)
