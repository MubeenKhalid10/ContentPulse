"""Posts and versions (spec §24, §25, §40). Copy is never edited in place:
every save, regeneration or restore adds a version (spec rule 4)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppError,
    Conflict,
    ErrorCode,
    Forbidden,
    InvalidStateTransition,
    NotFound,
)
from app.core.logging import logger
from app.models.ai import AIGenerationJob
from app.models.approval import ApprovalRequest
from app.models.design import CreativeAsset
from app.models.enums import (
    ApprovalStatus,
    JobStatus,
    Platform,
    PostStatus,
    StrategyStatus,
    TopicStatus,
    VersionSource,
)
from app.models.organization import BrandProfile
from app.models.post import Post, PostVersion
from app.models.topic import ContentStrategy, TopicCandidate
from app.schemas.content import (
    DesignTaskRef,
    GenerationStatus,
    Limits,
    PostDetail,
    PostListItem,
    PostPage,
    TopicRef,
    VersionRead,
)
from app.schemas.topic import StrategyRead
from app.services import audit
from app.services.approvals import workflow as approvals
from app.services.audit import AuditAction
from app.services.content import blog, generation
from app.services.content.copy import check_copy
from app.services.design import brief_state
from app.services.design import service as design
from app.services.design.lookup import current_brief
from app.services.topics.platforms import PLATFORM_LABELS, get_rules
from app.services.workflow import transition_post
from app.storage import get_storage

P = PostStatus
# Copy can be changed while it is a draft. Once it is sent to an admin it is
# locked: the writer can withdraw it from review to edit again, or the admin
# decides. After approval it opens again only when an admin asks for copy
# changes (request changes with the copy in scope, or "Take back from design").
EDITABLE = (P.DRAFT,)
LOCKED_MESSAGE = (
    "This copy has been approved, so it's locked. An admin can request changes to reopen it."
)
IN_REVIEW_MESSAGE = (
    "This copy is with an admin for approval, so it's locked. "
    "Withdraw it from review to change it, or wait for the decision."
)
STATUS_GROUPS: dict[str, list[PostStatus] | None] = {
    "drafts": [P.DRAFT],
    # Sent back by an approver (see _group_clause).
    "changes": [P.DRAFT, P.CHANGES_REQUESTED],
    "design": [P.DESIGN_PENDING, P.DESIGN_IN_PROGRESS, P.DESIGN_UPLOADED],
    # Approval status on Write posts: copy waiting for approval, or approved
    # (the post has moved on to design or is ready).
    "approval": [
        P.CONTENT_REVIEW,
        P.DESIGN_PENDING,
        P.DESIGN_IN_PROGRESS,
        P.DESIGN_UPLOADED,
        P.PENDING_APPROVAL,
        P.APPROVED,
        P.FINAL,
    ],
    # "Sent for approval", split: still waiting on an admin / already past that step.
    "approval_pending": [P.CONTENT_REVIEW, P.PENDING_APPROVAL],
    "approval_done": [
        P.DESIGN_PENDING,
        P.DESIGN_IN_PROGRESS,
        P.DESIGN_UPLOADED,
        P.APPROVED,
        P.FINAL,
    ],
    "approved": [P.APPROVED, P.FINAL],
    "archived": [P.ARCHIVED, P.REJECTED],
    "all": None,
}
# Changes requested on the copy put the post back to DRAFT; on the design
# they leave it CHANGES_REQUESTED.
_LATEST_REVIEW = (
    select(ApprovalRequest.status)
    .where(ApprovalRequest.post_id == Post.id)
    .order_by(ApprovalRequest.created_at.desc())
    .limit(1)
    .scalar_subquery()
)
# What the latest change request opened (no recorded scope counts as both), as in
# approvals.changes_scope.
_CHANGES_SCOPE = (
    select(func.coalesce(ApprovalRequest.scope, "both"))
    .where(
        ApprovalRequest.post_id == Post.id,
        ApprovalRequest.status == ApprovalStatus.CHANGES_REQUESTED,
    )
    .order_by(ApprovalRequest.reviewed_at.desc(), ApprovalRequest.created_at.desc())
    .limit(1)
    .scalar_subquery()
)
# Sent back with the copy to change. Design-only changes are the designer's work: they
# show on Add designs, not here.
SENT_BACK = or_(
    and_(Post.status == P.CHANGES_REQUESTED, _CHANGES_SCOPE.is_distinct_from("design")),
    # IS NOT DISTINCT FROM: a never-reviewed draft (no request, NULL) is not sent back.
    and_(
        Post.status == P.DRAFT,
        _LATEST_REVIEW.is_not_distinct_from(ApprovalStatus.CHANGES_REQUESTED),
    ),
)


def _group_clause(group: str):
    statuses = STATUS_GROUPS[group]
    clause = Post.status.in_(statuses) if statuses is not None else true()
    if group == "drafts":
        return and_(clause, ~SENT_BACK)
    if group == "changes":
        return and_(clause, SENT_BACK)
    return clause


COPY_FIELDS = ("hook", "body", "cta", "hashtags", "mentions")
DESIGN_STATUSES = (P.DESIGN_PENDING, P.DESIGN_IN_PROGRESS, P.DESIGN_UPLOADED)
META_FIELDS = ("visual_concept", "design_format", "blog")


def _generation(job: AIGenerationJob | None) -> GenerationStatus | None:
    if job is None:
        return None
    status = job.status
    stale = job.created_at < datetime.now(UTC) - generation.STALE_AFTER
    if status in (JobStatus.QUEUED, JobStatus.RUNNING) and stale:
        status = JobStatus.FAILED  # interrupted (e.g. server restart)
    return GenerationStatus(
        job_id=job.id,
        kind=job.result.get("kind", "generate"),
        status=status,
        engine="template" if job.provider == "template" else "ai",
        error=job.error
        if job.status == JobStatus.FAILED
        else ("Generation was interrupted. Try again." if status == JobStatus.FAILED else None),
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


async def _get_post(
    db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID, *, lock: bool = False
) -> Post:
    """`lock` holds the row until commit: use it when the status is checked and
    then changed, so a double click or a second admin waits and sees the result."""
    query = select(Post).where(Post.id == post_id, Post.organization_id == organization_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    post = await db.scalar(query)
    if post is None:
        raise NotFound("Post")
    return post


async def _current(db: AsyncSession, post: Post) -> PostVersion | None:
    if not post.current_version:
        return None
    return await db.scalar(
        select(PostVersion).where(
            PostVersion.post_id == post.id, PostVersion.version_number == post.current_version
        )
    )


async def _items(db: AsyncSession, posts: list[Post]) -> list[PostListItem]:
    ids = [p.id for p in posts]
    jobs = await generation.latest_jobs(db, ids)
    hooks = (
        dict(
            (
                await db.execute(
                    select(PostVersion.post_id, PostVersion.hook)
                    .join(Post, Post.id == PostVersion.post_id)
                    .where(
                        PostVersion.post_id.in_(ids),
                        PostVersion.version_number == Post.current_version,
                    )
                )
            ).all()
        )
        if ids
        else {}
    )
    sent_back = [p.id for p in posts if p.status in (P.DRAFT, P.CHANGES_REQUESTED)]
    scopes: dict[uuid.UUID, str] = (
        dict(
            (
                await db.execute(
                    select(Post.id, _CHANGES_SCOPE).where(
                        Post.id.in_(sent_back),
                        or_(
                            Post.status == P.CHANGES_REQUESTED,
                            _LATEST_REVIEW == ApprovalStatus.CHANGES_REQUESTED,
                        ),
                    )
                )
            ).all()
        )
        if sent_back
        else {}
    )
    topic_ids = {p.topic_id for p in posts if p.topic_id}
    topics = {
        t.id: t
        for t in (
            await db.scalars(select(TopicCandidate).where(TopicCandidate.id.in_(topic_ids)))
            if topic_ids
            else []
        )
    }
    return [
        PostListItem(
            id=p.id,
            title=p.title,
            platform=p.platform,
            status=p.status,
            current_version=p.current_version,
            hook=hooks.get(p.id),
            topic=TopicRef(id=t.id, title=t.title, status=t.status)
            if (t := topics.get(p.topic_id))
            else None,
            content_strategy_id=p.content_strategy_id,
            variant_of_id=p.variant_of_id,
            generation=_generation(jobs.get(p.id)),
            # Copy sent back at copy approval puts the post back to draft: copy only.
            changes_scope=("copy" if p.status == P.DRAFT else scopes[p.id])
            if p.id in scopes
            else None,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in posts
    ]


async def list_posts(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    platform: str | None,
    topic_id: uuid.UUID | None,
    q: str | None,
    limit: int,
    offset: int,
) -> PostPage:
    filters = [Post.organization_id == organization_id]
    if platform:
        filters.append(Post.platform == Platform(platform))
    if topic_id:
        filters.append(Post.topic_id == topic_id)
    if q:
        pattern = f"%{q.strip()}%"
        matching_versions = select(PostVersion.post_id).where(
            PostVersion.organization_id == organization_id,
            or_(PostVersion.hook.ilike(pattern), PostVersion.body.ilike(pattern)),
        )
        filters.append(or_(Post.title.ilike(pattern), Post.id.in_(matching_versions)))
    row = (
        await db.execute(
            select(*(func.count().filter(_group_clause(g)) for g in STATUS_GROUPS)).where(*filters)
        )
    ).one()
    counts = dict(zip(STATUS_GROUPS, row, strict=True))
    filters.append(_group_clause(status))
    total = await db.scalar(select(func.count()).select_from(Post).where(*filters))
    posts = list(
        await db.scalars(
            select(Post)
            .where(*filters)
            .order_by(Post.updated_at.desc(), Post.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return PostPage(items=await _items(db, posts), total=total or 0, counts=counts)


async def post_detail(
    db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    [item] = await _items(db, [post])
    current = await _current(db, post)
    strategy = (
        await db.get(ContentStrategy, post.content_strategy_id)
        if post.content_strategy_id
        else None
    )
    root = post.variant_of_id or post.id
    siblings = list(
        await db.scalars(
            select(Post)
            .where(
                Post.organization_id == organization_id,
                or_(Post.id == root, Post.variant_of_id == root),
                Post.id != post.id,
            )
            .order_by(Post.created_at)
        )
    )
    rule = (await get_rules(db, organization_id))[Platform(post.platform)]
    brief = await current_brief(db, post.id)
    await db.commit()  # keep seeded platform rules
    return PostDetail(
        **item.model_dump(),
        current=VersionRead.model_validate(current) if current else None,
        strategy=StrategyRead.model_validate(strategy) if strategy else None,
        variants=await _items(db, siblings),
        limits=Limits(max_length=rule.max_length, hashtag_limit=rule.hashtag_limit),
        editable=await copy_editable(db, post),
        design_task=DesignTaskRef(id=brief.id, status=brief.status) if brief else None,
        review=await approvals.latest_review(db, post.id),
        creatives=await design.creative_versions(db, post.id),
    )


async def list_versions(
    db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID
) -> list[VersionRead]:
    post = await _get_post(db, organization_id, post_id)
    rows = await db.scalars(
        select(PostVersion)
        .where(PostVersion.post_id == post.id)
        .order_by(PostVersion.version_number.desc())
    )
    return [VersionRead.model_validate(v) for v in rows]


# --- Generation entry points ---------------------------------------------------------


async def generate(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, strategy_id: uuid.UUID
) -> PostDetail:
    """Spec §40 POST /content/generate: a new post from a plan (strategy).
    Writing the post approves a draft plan: there is no separate approval step."""
    strategy = await db.scalar(
        select(ContentStrategy).where(
            ContentStrategy.id == strategy_id, ContentStrategy.organization_id == organization_id
        )
    )
    if strategy is None:
        raise NotFound("Strategy")
    if strategy.status == StrategyStatus.ARCHIVED:
        raise InvalidStateTransition(
            "This plan is archived. Create a new plan to write a post.",
            details={"status": strategy.status.value},
        )
    topic = await db.get(TopicCandidate, strategy.topic_id)
    if strategy.status == StrategyStatus.DRAFT:
        if topic is None or topic.status != TopicStatus.SHORTLISTED:
            raise InvalidStateTransition("Shortlist the topic before writing posts for it.")
        strategy.status = StrategyStatus.APPROVED
        strategy.approved_by, strategy.approved_at = user_id, datetime.now(UTC)
        audit.record(
            db,
            organization_id=organization_id,
            user_id=user_id,
            action=AuditAction.STRATEGY_APPROVED,
            entity_type="content_strategy",
            entity_id=strategy.id,
            old_value={"status": StrategyStatus.DRAFT},
            new_value={"status": StrategyStatus.APPROVED, "platform": strategy.platform},
        )
        await db.flush()
        await db.refresh(strategy)  # load the new updated_at before serializing
    post = Post(
        organization_id=organization_id,
        topic_id=strategy.topic_id,
        content_strategy_id=strategy.id,
        platform=strategy.platform,
        title=topic.title if topic else None,
        created_by=user_id,
    )
    db.add(post)
    await db.flush()
    _record(db, post, user_id, AuditAction.CONTENT_GENERATED, {"kind": "generate"})
    await generation.start(db, post, kind="generate", user_id=user_id)
    return await post_detail(db, organization_id, post.id)


async def copy_editable(db: AsyncSession, post: Post) -> bool:
    if post.status in EDITABLE:
        return True
    if post.status != P.CHANGES_REQUESTED:
        return False
    return await approvals.changes_scope(db, post.id) in ("copy", "both")


async def _require_editable(db: AsyncSession, post: Post) -> None:
    if not await copy_editable(db, post):
        message = IN_REVIEW_MESSAGE if post.status == P.CONTENT_REVIEW else LOCKED_MESSAGE
        raise InvalidStateTransition(message, details={"status": post.status.value})


async def regenerate(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    instructions: str | None,
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    await _require_editable(db, post)
    _record(db, post, user_id, AuditAction.CONTENT_GENERATED, {"kind": "regenerate"})
    await generation.start(db, post, kind="regenerate", instructions=instructions, user_id=user_id)
    return await post_detail(db, organization_id, post.id)


async def create_variant(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, post_id: uuid.UUID
) -> PostDetail:
    source = await _get_post(db, organization_id, post_id)
    if source.content_strategy_id is None:
        raise Conflict("This post has no content strategy to build a variant from.")
    variant = Post(
        organization_id=organization_id,
        topic_id=source.topic_id,
        content_strategy_id=source.content_strategy_id,
        platform=source.platform,
        title=source.title,
        variant_of_id=source.variant_of_id or source.id,
        created_by=user_id,
    )
    db.add(variant)
    await db.flush()
    _record(db, variant, user_id, AuditAction.CONTENT_GENERATED, {"kind": "variant"})
    await generation.start(db, variant, kind="variant", source_post_id=source.id, user_id=user_id)
    return await post_detail(db, organization_id, variant.id)


async def delete_post(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    *,
    any_stage: bool = False,
) -> None:
    """Writers can delete a post with nothing written (its writing failed).
    An admin (`any_stage`) can delete a post at any stage: its versions,
    design task, creative files and approvals go with it."""
    post = await _get_post(db, organization_id, post_id)
    if not any_stage and (post.current_version or post.status != P.DRAFT):
        raise Conflict(
            "Only a post whose writing failed, with nothing written yet, can be deleted. "
            "An admin can delete any post."
        )
    if await generation.active_job(db, post.id):
        raise Conflict("This post is still being written.")
    keys = set(
        await db.scalars(select(CreativeAsset.storage_key).where(CreativeAsset.post_id == post.id))
    )
    _record(
        db,
        post,
        user_id,
        AuditAction.CONTENT_DELETED,
        {
            "title": post.title,
            "platform": post.platform.value,
            "status": post.status.value,
            "versions": post.current_version,
        },
    )
    await db.delete(post)
    await db.commit()
    # The files are no longer referenced; a missing one is not worth failing for.
    storage = get_storage()
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not remove creative file %s", key)


# --- Editing ----------------------------------------------------------------------


async def update_post(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    data: dict[str, Any],
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id, lock=True)
    base = data.pop("base_version")
    note = data.pop("change_note", None)
    if "title" in data and data["title"] != post.title:
        await _require_editable(db, post)  # a title is copy: locked with it
        old, new = audit.diff(post, {"title": data["title"]})
        post.title = data["title"]
        _record(db, post, user_id, AuditAction.CONTENT_EDITED, new, old)
    data.pop("title", None)
    if data.get("blog") is not None and post.platform != Platform.BLOG:
        message = "SEO details only apply to blog posts."
        raise AppError(
            ErrorCode.VALIDATION_ERROR, message, details=[{"field": "blog", "message": message}]
        )
    if data:
        await _require_editable(db, post)
        if await generation.active_job(db, post.id):
            raise Conflict("This post is being generated. Wait for it to finish before editing.")
        if base != post.current_version:
            raise Conflict(
                f"Someone saved version {post.current_version} while you were editing "
                f"version {base}. Reload to see their changes."
            )
        current = await _current(db, post)
        fields = {
            "hook": current.hook if current else None,
            "body": current.body if current else None,
            "cta": current.cta if current else None,
            "hashtags": current.hashtags if current else [],
            "mentions": current.mentions if current else [],
        }
        meta = dict(current.meta) if current else {}
        if "blog" in data:
            data["blog"] = {**(meta.get("blog") or {}), **(data["blog"] or {})}
        changed = {k: v for k, v in data.items() if k in COPY_FIELDS and v != fields[k]}
        changed_meta = {k: v for k, v in data.items() if k in META_FIELDS and v != meta.get(k)}
        if changed or changed_meta:
            fields |= changed
            meta |= changed_meta
            await _add_version(
                db, post, user_id, fields, meta, note or _describe(changed, changed_meta)
            )
    try:
        await db.commit()
    except IntegrityError as exc:  # two saves raced for the same version number
        await db.rollback()
        raise Conflict("Someone saved this post while you were editing. Reload to see it.") from exc
    return await post_detail(db, organization_id, post.id)


def _describe(changed: dict, changed_meta: dict) -> str:
    names = {
        "hook": "hook",
        "body": "body",
        "cta": "call to action",
        "hashtags": "hashtags",
        "mentions": "mentions",
        "visual_concept": "visual concept",
        "design_format": "format",
        "blog": "SEO details",
    }
    edited = [names[k] for k in [*changed, *changed_meta]]
    return "Edited " + ", ".join(edited)


async def _add_version(
    db: AsyncSession,
    post: Post,
    user_id: uuid.UUID,
    fields: dict[str, Any],
    meta: dict[str, Any],
    note: str,
) -> None:
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == post.organization_id)
    )
    rule = (await get_rules(db, post.organization_id))[Platform(post.platform)]
    meta = {
        k: v
        for k, v in meta.items()
        if k not in ("engine", "model", "prompt", "corrections", "instructions", "kind")
    }
    meta["warnings"] = check_copy(
        **{k: fields[k] for k in ("hook", "body", "cta", "hashtags")},
        forbidden_terms=brand.forbidden_terms if brand else [],
        max_length=rule.max_length,
        hashtag_limit=rule.hashtag_limit,
        platform_label=PLATFORM_LABELS[post.platform],
    )
    if post.platform == Platform.BLOG:
        meta["warnings"] += blog.check_blog(meta.get("blog"), fields["hook"], fields["body"])
    meta["edited_from"] = post.current_version
    number = post.current_version + 1
    db.add(
        PostVersion(
            organization_id=post.organization_id,
            post_id=post.id,
            version_number=number,
            meta=meta,
            source=VersionSource.MANUAL,
            change_note=note,
            created_by=user_id,
            **fields,
        )
    )
    post.current_version = number
    _record(db, post, user_id, AuditAction.CONTENT_EDITED, {"version": number, "note": note})


async def restore_version(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    number: int,
    base_version: int,
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    await _require_editable(db, post)
    if base_version != post.current_version:
        raise Conflict("The post changed since you opened it. Reload and try again.")
    version = await db.scalar(
        select(PostVersion).where(
            PostVersion.post_id == post.id, PostVersion.version_number == number
        )
    )
    if version is None:
        raise NotFound("Version")
    if number == post.current_version:
        raise Conflict("That's already the current version.")
    fields = {k: getattr(version, k) for k in COPY_FIELDS}
    await _add_version(db, post, user_id, fields, dict(version.meta), f"Restored version {number}")
    await db.commit()
    return await post_detail(db, organization_id, post.id)


# --- Workflow (spec §25, §54) ------------------------------------------------------------

ACTIONS: dict[str, PostStatus] = {
    "back-to-draft": P.DRAFT,
    "submit-for-review": P.CONTENT_REVIEW,
    "archive": P.ARCHIVED,
}


async def transition(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    action: str,
    *,
    can_review: bool = False,
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id, lock=True)
    target = ACTIONS[action]
    if target == P.DRAFT and post.status not in (*EDITABLE, P.CONTENT_REVIEW) and not can_review:
        # Back to draft reopens approved copy: an admin's call.
        raise Forbidden("Only an admin can reopen approved copy.")
    if target == P.ARCHIVED and post.status not in (*EDITABLE, P.CONTENT_REVIEW) and not can_review:
        # Archiving is terminal: past review it discards approved work.
        raise Forbidden("Only an admin can archive approved content.")
    if target == P.CONTENT_REVIEW:
        if not post.current_version:
            raise InvalidStateTransition("Generate or write the post before moving it on.")
        if await generation.active_job(db, post.id):
            raise Conflict("This post is being generated. Wait for it to finish.")
    previous = post.status
    if target == P.CONTENT_REVIEW:
        await approvals.submit_copy(db, post, user_id)
    else:
        await transition_post(db, post, target, user_id=user_id)
        if previous == P.CONTENT_REVIEW:
            await approvals.withdraw_copy(db, post)
        elif previous in (*DESIGN_STATUSES, P.CHANGES_REQUESTED):
            # A post sent back for design changes has an open task too.
            await brief_state.cancel_open(db, post.id)
    await db.commit()
    return await post_detail(db, organization_id, post.id)


async def resubmit(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    note: str | None,
) -> PostDetail:
    """After copy-only changes: send the post back for approval with its
    existing creative (spec §32 "Re-submit")."""
    post = await _get_post(db, organization_id, post_id, lock=True)
    if await generation.active_job(db, post.id):
        raise Conflict("This post is being generated. Wait for it to finish.")
    await approvals.submit_post(db, post, user_id, note)
    await db.commit()
    return await post_detail(db, organization_id, post.id)


def _record(
    db: AsyncSession,
    post: Post,
    user_id: uuid.UUID,
    action: AuditAction,
    new: dict,
    old: dict | None = None,
) -> None:
    audit.record(
        db,
        organization_id=post.organization_id,
        user_id=user_id,
        action=action,
        entity_type="post",
        entity_id=post.id,
        old_value=old,
        new_value={"platform": post.platform, **new},
    )
