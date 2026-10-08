"""Approvals (spec §31-33, §42, §53): the review queue, the review page, and
the decisions that move a post to APPROVED, CHANGES_REQUESTED or REJECTED."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import InvalidStateTransition, NotFound
from app.models.approval import ApprovalComment, ApprovalRequest
from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import ApprovalStatus, DesignBriefStatus, PostStatus
from app.models.post import Post, PostVersion
from app.models.topic import TopicCandidate
from app.models.trend import Trend, TrendMention
from app.models.user import User
from app.schemas.approval import (
    ApprovalDetail,
    ApprovalListItem,
    ApprovalPage,
    ApprovalPost,
    BriefSummary,
    CommentRead,
    Round,
    TopicContext,
)
from app.schemas.content import VersionRead
from app.services import audit
from app.services.audit import AuditAction
from app.services.design.service import creative_versions, person
from app.services.workflow import transition_post
from app.storage import get_storage

A = ApprovalStatus
FILTERS: dict[str, list[ApprovalStatus] | None] = {
    "pending": [A.PENDING],
    "reviewed": [A.APPROVED, A.CHANGES_REQUESTED, A.REJECTED],
    "approved": [A.APPROVED],
    "changes_requested": [A.CHANGES_REQUESTED],
    "rejected": [A.REJECTED],
    "all": None,
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _get(
    db: AsyncSession, organization_id: uuid.UUID, request_id: uuid.UUID
) -> ApprovalRequest:
    request = await db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == request_id, ApprovalRequest.organization_id == organization_id
        )
    )
    if request is None:
        raise NotFound("Approval")
    return request


async def _users(db: AsyncSession, ids: set) -> dict[uuid.UUID, User]:
    ids = {i for i in ids if i}
    return {u.id: u for u in await db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


async def _items(db: AsyncSession, requests: list[ApprovalRequest]) -> list[ApprovalListItem]:
    if not requests:
        return []
    post_ids = {r.post_id for r in requests}
    posts = {p.id: p for p in await db.scalars(select(Post).where(Post.id.in_(post_ids)))}
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
    users = await _users(db, {r.submitted_by for r in requests} | {r.reviewer_id for r in requests})
    ranked = (
        select(
            ApprovalRequest.id,
            func.row_number()
            .over(partition_by=ApprovalRequest.post_id, order_by=ApprovalRequest.created_at)
            .label("round"),
        )
        .where(ApprovalRequest.post_id.in_(post_ids))
        .subquery()
    )
    rounds = dict((await db.execute(select(ranked.c.id, ranked.c.round))).all())
    comment_counts = dict(
        (
            await db.execute(
                select(ApprovalComment.approval_request_id, func.count())
                .where(ApprovalComment.approval_request_id.in_([r.id for r in requests]))
                .group_by(ApprovalComment.approval_request_id)
            )
        ).all()
    )
    # Preview: the first image of the creative version under review.
    previews: dict[tuple[uuid.UUID, int], CreativeAsset] = {}
    for asset in await db.scalars(
        select(CreativeAsset)
        .where(CreativeAsset.post_id.in_(post_ids), CreativeAsset.file_type.like("image/%"))
        .order_by(CreativeAsset.position)
    ):
        previews.setdefault((asset.post_id, asset.version), asset)
    storage = get_storage()
    items = []
    for r in requests:
        post = posts[r.post_id]
        preview = previews.get((r.post_id, r.creative_version or 0))
        items.append(
            ApprovalListItem(
                id=r.id,
                status=r.status,
                round=rounds.get(r.id, 1),
                post=ApprovalPost(
                    id=post.id,
                    title=post.title,
                    platform=post.platform,
                    status=post.status,
                    current_version=post.current_version,
                ),
                topic_title=topics.get(post.topic_id),
                post_version=r.post_version,
                creative_version=r.creative_version,
                preview_url=await storage.download_url(preview.storage_key, preview.file_name)
                if preview
                else None,
                submitted_by=person(users.get(r.submitted_by)),
                reviewer=person(users.get(r.reviewer_id)),
                comment_count=comment_counts.get(r.id, 0),
                created_at=r.created_at,
                reviewed_at=r.reviewed_at,
            )
        )
    return items


async def list_approvals(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    platform: str | None,
    limit: int,
    offset: int,
) -> ApprovalPage:
    # One row per post: its latest round. Earlier rounds are history, shown on the
    # review page, so a resubmitted post never appears twice.
    newer = aliased(ApprovalRequest)
    superseded = (
        select(newer.id)
        .where(
            newer.post_id == ApprovalRequest.post_id,
            newer.created_at > ApprovalRequest.created_at,
        )
        .exists()
    )
    filters = [ApprovalRequest.organization_id == organization_id, ~superseded]
    if platform:
        filters.append(
            ApprovalRequest.post_id.in_(
                select(Post.id).where(
                    Post.organization_id == organization_id, Post.platform == platform
                )
            )
        )
    by_status = dict(
        (
            await db.execute(
                select(ApprovalRequest.status, func.count())
                .where(*filters)
                .group_by(ApprovalRequest.status)
            )
        ).all()
    )
    counts = {
        name: sum(by_status.get(s, 0) for s in statuses) if statuses else sum(by_status.values())
        for name, statuses in FILTERS.items()
    }
    if (statuses := FILTERS[status]) is not None:
        filters.append(ApprovalRequest.status.in_(statuses))
    total = await db.scalar(select(func.count()).select_from(ApprovalRequest).where(*filters))
    # The queue is first come, first served; history shows the latest first.
    order = (
        [ApprovalRequest.created_at]
        if status == "pending"
        else [nulls_last(ApprovalRequest.reviewed_at.desc()), ApprovalRequest.created_at.desc()]
    )
    rows = list(
        await db.scalars(
            select(ApprovalRequest)
            .where(*filters)
            .order_by(*order, ApprovalRequest.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return ApprovalPage(items=await _items(db, rows), total=total or 0, counts=counts)


async def _comments(db: AsyncSession, post_id: uuid.UUID) -> list[CommentRead]:
    rows = list(
        await db.scalars(
            select(ApprovalComment)
            .where(ApprovalComment.post_id == post_id)
            .order_by(ApprovalComment.created_at)
        )
    )
    users = await _users(db, {c.author_id for c in rows})
    return [
        CommentRead(
            id=c.id,
            approval_request_id=c.approval_request_id,
            post_version=c.post_version,
            creative_version=c.creative_version,
            kind=c.kind,
            body=c.body,
            author=person(users.get(c.author_id)),
            created_at=c.created_at,
        )
        for c in rows
    ]


async def _topic_context(db: AsyncSession, post: Post) -> TopicContext | None:
    topic = await db.get(TopicCandidate, post.topic_id) if post.topic_id else None
    if topic is None:
        return None
    trend = await db.get(Trend, topic.trend_id) if topic.trend_id else None
    coverage = []
    if trend:
        mentions = await db.scalars(
            select(TrendMention)
            .where(TrendMention.trend_id == trend.id, TrendMention.source_url.is_not(None))
            .order_by(nulls_last(TrendMention.engagement.desc()))
            .limit(5)
        )
        coverage = [{"title": m.title, "url": m.source_url, "source": m.source} for m in mentions]
    return TopicContext(
        id=topic.id,
        title=topic.title,
        relevance_level=topic.relevance_level,
        relevance_reason=topic.relevance_reason,
        trend_id=topic.trend_id,
        sources=trend.sources if trend else [],
        coverage=coverage,
    )


async def approval_detail(
    db: AsyncSession, organization_id: uuid.UUID, request_id: uuid.UUID
) -> ApprovalDetail:
    request = await _get(db, organization_id, request_id)
    [item] = await _items(db, [request])
    post = await db.get(Post, request.post_id)
    assert post is not None
    versions = [
        VersionRead.model_validate(v)
        for v in await db.scalars(
            select(PostVersion)
            .where(PostVersion.post_id == post.id)
            .order_by(PostVersion.version_number.desc())
        )
    ]
    submitted = next((v for v in versions if v.version_number == request.post_version), None)
    creatives = await creative_versions(db, post.id)
    brief = await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post.id, DesignBrief.status != DesignBriefStatus.CANCELLED)
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )
    all_rounds = list(
        await db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.post_id == post.id)
            .order_by(ApprovalRequest.created_at)
        )
    )
    users = await _users(
        db, {r.submitted_by for r in all_rounds} | {r.reviewer_id for r in all_rounds}
    )
    return ApprovalDetail(
        **item.model_dump(),
        content=submitted,
        copy_changed_since=post.current_version != request.post_version,
        creative=next((c for c in creatives if c.version == request.creative_version), None),
        creatives=creatives,
        versions=versions,
        brief=BriefSummary(
            id=brief.id,
            format=brief.format,
            dimensions=brief.dimensions,
            headline=brief.headline,
            visual_concept=brief.visual_concept,
            slide_structure=brief.slide_structure,
            cta=brief.cta,
            designer_notes=brief.designer_notes,
        )
        if brief
        else None,
        topic=await _topic_context(db, post),
        comments=await _comments(db, post.id),
        rounds=[
            Round(
                id=r.id,
                status=r.status,
                post_version=r.post_version,
                creative_version=r.creative_version,
                submitted_by=person(users.get(r.submitted_by)),
                reviewer=person(users.get(r.reviewer_id)),
                created_at=r.created_at,
                reviewed_at=r.reviewed_at,
            )
            for r in all_rounds
        ],
        strategy_id=post.content_strategy_id,
    )


# --- Decisions ----------------------------------------------------------------------

DECISIONS = {
    A.APPROVED: (PostStatus.APPROVED, AuditAction.APPROVED, "approved"),
    A.CHANGES_REQUESTED: (
        PostStatus.CHANGES_REQUESTED,
        AuditAction.CHANGES_REQUESTED,
        "changes_requested",
    ),
    A.REJECTED: (PostStatus.REJECTED, AuditAction.REJECTED, "rejected"),
}


def _comment(request: ApprovalRequest, user_id: uuid.UUID, body: str, kind: str) -> ApprovalComment:
    """Pinned to the exact copy and creative versions reviewed (spec §33)."""
    return ApprovalComment(
        organization_id=request.organization_id,
        approval_request_id=request.id,
        post_id=request.post_id,
        post_version=request.post_version,
        creative_version=request.creative_version,
        author_id=user_id,
        body=body,
        kind=kind,
    )


async def decide(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: uuid.UUID,
    decision: ApprovalStatus,
    comment: str | None,
    scope: str = "both",
) -> ApprovalDetail:
    request = await _get(db, organization_id, request_id)
    if request.status != A.PENDING:
        raise InvalidStateTransition(
            "This submission has already been reviewed.",
            details={"status": request.status.value},
        )
    post = await db.get(Post, request.post_id)
    assert post is not None
    target, action, kind = DECISIONS[decision]
    await transition_post(db, post, target, user_id=user_id)
    if decision == A.APPROVED:
        # One click: approved posts are locked and ready to publish.
        await transition_post(db, post, PostStatus.FINAL, user_id=user_id)

    request.status, request.reviewer_id, request.reviewed_at = decision, user_id, _now()
    request.comments = comment
    if comment:
        db.add(_comment(request, user_id, comment, kind))

    brief = await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post.id, DesignBrief.status == DesignBriefStatus.SUBMITTED)
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )
    if brief is not None:
        if decision == A.APPROVED:
            brief.status = DesignBriefStatus.COMPLETED
        elif decision == A.REJECTED:
            brief.status = DesignBriefStatus.CANCELLED
        elif scope in ("design", "both"):
            # Back on the designer's to-do list, with the same assignee.
            brief.status = DesignBriefStatus.IN_PROGRESS
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        entity_type="post",
        entity_id=post.id,
        new_value={
            "approval_request_id": request.id,
            "post_version": request.post_version,
            "creative_version": request.creative_version,
            **({"scope": scope} if decision == A.CHANGES_REQUESTED else {}),
        },
    )
    await db.commit()
    return await approval_detail(db, organization_id, request.id)


async def finalize(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, request_id: uuid.UUID
) -> ApprovalDetail:
    """Spec §32/§54: APPROVED → FINAL, the post is locked and ready to publish."""
    request = await _get(db, organization_id, request_id)
    post = await db.get(Post, request.post_id)
    assert post is not None
    if request.status != A.APPROVED:
        raise InvalidStateTransition("Only an approved submission can be marked final.")
    await transition_post(db, post, PostStatus.FINAL, user_id=user_id)
    await db.commit()
    return await approval_detail(db, organization_id, request.id)


async def add_comment(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: uuid.UUID,
    body: str,
) -> ApprovalDetail:
    request = await _get(db, organization_id, request_id)
    db.add(_comment(request, user_id, body, "comment"))
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.APPROVAL_COMMENTED,
        entity_type="post",
        entity_id=request.post_id,
        new_value={"approval_request_id": request.id, "post_version": request.post_version},
    )
    await db.commit()
    return await approval_detail(db, organization_id, request.id)
