"""Submitting a post for approval (spec §30-32). Shared by the design task
("Submit for approval") and the content studio ("Resubmit" after copy-only
changes), so every round records exactly what was reviewed."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransition
from app.models.approval import ApprovalComment, ApprovalRequest
from app.models.design import CreativeAsset
from app.models.enums import ApprovalStatus, PostStatus
from app.models.post import Post
from app.models.user import User
from app.schemas.design import ChangeRequestRead, Person, ReviewComment, ReviewSummary
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.design import brief_state
from app.services.design.lookup import current_brief
from app.services.workflow import transition_post

SUBMITTABLE = (PostStatus.DESIGN_UPLOADED, PostStatus.CHANGES_REQUESTED)


async def latest_creative_version(db: AsyncSession, post_id: uuid.UUID) -> int | None:
    return await db.scalar(
        select(func.max(CreativeAsset.version)).where(CreativeAsset.post_id == post_id)
    )


async def _tell_admins(
    db: AsyncSession, post: Post, user_id: uuid.UUID, request: ApprovalRequest, stage: str
) -> None:
    """A submission reaches the admins' queue; they hear about it once. After a change
    request the message says what was redone: the scope the admin asked for."""
    previous = await db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.post_id == post.id, ApprovalRequest.id != request.id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )
    again = previous is not None and previous.status == ApprovalStatus.CHANGES_REQUESTED
    scope = stage
    word = notifications.SCOPE_WORD[scope]
    name = notifications.post_name(post)
    await notifications.notify(
        db,
        organization_id=post.organization_id,
        user_ids=await notifications.admin_ids(db, post.organization_id),
        post=post,
        kind="resubmitted" if again else "submitted",
        scope=scope,
        title=(
            f"{name} was resubmitted ({word})"
            if again
            else f"{name} is waiting for your review ({word})"
        ),
        link=f"/approvals/{request.id}",
        dedupe_key=f"submitted:{request.id}",
        skip=user_id,
    )


async def submit_post(
    db: AsyncSession, post: Post, user_id: uuid.UUID, note: str | None = None
) -> ApprovalRequest:
    """DESIGN_UPLOADED (or CHANGES_REQUESTED with a creative) → PENDING_APPROVAL,
    opening a new review round pinned to the current copy and creative."""
    creative = await latest_creative_version(db, post.id)
    if creative is not None and post.status in (
        PostStatus.DESIGN_PENDING,
        PostStatus.DESIGN_IN_PROGRESS,
    ):
        # The files are there but the post was never moved on (e.g. an interrupted
        # upload or AI image): record that the design is added, then submit.
        await transition_post(db, post, PostStatus.DESIGN_UPLOADED, user_id=user_id)
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
    brief = await current_brief(db, post.id)
    if brief is not None:
        brief_state.mark_submitted(brief)
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
    await _tell_admins(db, post, user_id, request, "design")
    return request


async def submit_copy(
    db: AsyncSession, post: Post, user_id: uuid.UUID, note: str | None = None
) -> ApprovalRequest:
    """DRAFT → CONTENT_REVIEW: an admin approves the written copy before design.
    The request has no creative version, which marks it as the copy stage."""
    await transition_post(db, post, PostStatus.CONTENT_REVIEW, user_id=user_id)
    request = ApprovalRequest(
        organization_id=post.organization_id,
        post_id=post.id,
        post_version=post.current_version,
        creative_version=None,
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
                creative_version=None,
                author_id=user_id,
                body=note,
                kind="resubmitted",
            )
        )
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
            "stage": "copy",
        },
    )
    await _tell_admins(db, post, user_id, request, "copy")
    return request


async def withdraw_copy(db: AsyncSession, post: Post) -> None:
    """Back to draft before anyone reviewed it: drop the open copy request."""
    for request in await db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.post_id == post.id,
            ApprovalRequest.creative_version.is_(None),
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
    ):
        await db.delete(request)


async def withdraw_design(db: AsyncSession, post: Post) -> None:
    """The designer took the design back before anyone decided: drop the open design request."""
    for request in await db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.post_id == post.id,
            ApprovalRequest.creative_version.is_not(None),
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
    ):
        await db.delete(request)


def shown_scope(scope: str | None) -> str:
    """ "copy" or "design". Older requests that covered both (or recorded nothing) count as
    design, where they are listed."""
    return "copy" if scope == "copy" else "design"


async def changes_scope(db: AsyncSession, post_id: uuid.UUID) -> str:
    """What the latest change request opened: "copy" or "design"."""
    scope = await db.scalar(
        select(ApprovalRequest.scope)
        .where(
            ApprovalRequest.post_id == post_id,
            ApprovalRequest.status == ApprovalStatus.CHANGES_REQUESTED,
        )
        .order_by(ApprovalRequest.reviewed_at.desc(), ApprovalRequest.created_at.desc())
        .limit(1)
    )
    return shown_scope(scope)


async def changes_scopes(db: AsyncSession, post_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """`changes_scope` for many posts in one query."""
    if not post_ids:
        return {}
    rows = await db.execute(
        select(ApprovalRequest.post_id, ApprovalRequest.scope)
        .where(
            ApprovalRequest.post_id.in_(post_ids),
            ApprovalRequest.status == ApprovalStatus.CHANGES_REQUESTED,
        )
        .ext(distinct_on(ApprovalRequest.post_id))
        .order_by(
            ApprovalRequest.post_id,
            ApprovalRequest.reviewed_at.desc(),
            ApprovalRequest.created_at.desc(),
        )
    )
    return {post_id: shown_scope(scope) for post_id, scope in rows.all()}


# A request is over when the post is rejected or archived; resubmitting opens a newer round.
_ENDED = (PostStatus.REJECTED, PostStatus.ARCHIVED)


async def current_change_requests(
    db: AsyncSession, posts: list[Post]
) -> dict[uuid.UUID, ChangeRequestRead]:
    """The change request each post is waiting on: its latest review round, if an admin sent
    it back and the creator hasn't resubmitted. A resubmission opens a newer round, so the
    old one stops being current and stays in the post's history."""
    waiting = [p for p in posts if p.status not in _ENDED]
    if not waiting:
        return {}
    latest = list(
        await db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.post_id.in_([p.id for p in waiting]))
            .ext(distinct_on(ApprovalRequest.post_id))
            .order_by(ApprovalRequest.post_id, ApprovalRequest.created_at.desc())
        )
    )
    open_rounds = [r for r in latest if r.status == ApprovalStatus.CHANGES_REQUESTED]
    if not open_rounds:
        return {}
    by_post = {p.id: p for p in waiting}
    creatives = dict(
        (
            await db.execute(
                select(CreativeAsset.post_id, func.max(CreativeAsset.version))
                .where(CreativeAsset.post_id.in_([r.post_id for r in open_rounds]))
                .group_by(CreativeAsset.post_id)
            )
        ).all()
    )
    user_ids = {r.reviewer_id for r in open_rounds if r.reviewer_id}
    users = (
        {u.id: u for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )
    reads = {}
    for r in open_rounds:
        post = by_post[r.post_id]
        # Older requests could cover both; they are shown as the design request they opened.
        scope = "copy" if r.scope == "copy" or r.creative_version is None else "design"
        wants_copy, wants_design = scope == "copy", scope == "design"
        reviewer = users.get(r.reviewer_id) if r.reviewer_id else None
        reads[r.post_id] = ChangeRequestRead(
            id=r.id,
            post_id=r.post_id,
            scope=scope,
            note=r.comments,
            status="open",
            requested_by=Person(id=reviewer.id, name=reviewer.full_name, email=reviewer.email)
            if reviewer
            else None,
            created_at=r.reviewed_at or r.created_at,
            # Each part is done once there is a newer version than the one that was reviewed.
            content_done=not wants_copy or post.current_version > r.post_version,
            design_done=not wants_design
            or (creatives.get(r.post_id) or 0) > (r.creative_version or 0),
        )
    return reads


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
    # Rounds count within a stage: the copy review is round 1 of its own.
    rounds = await db.scalar(
        select(func.count()).where(
            ApprovalRequest.post_id == post_id,
            ApprovalRequest.creative_version.is_(None) == (request.creative_version is None),
        )
    )
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
