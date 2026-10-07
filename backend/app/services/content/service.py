"""Posts and versions (spec §24, §25, §40). Copy is never edited in place:
every save, regeneration or restore adds a version (spec rule 4)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Conflict, ErrorCode, InvalidStateTransition, NotFound
from app.models.ai import AIGenerationJob
from app.models.enums import (
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
from app.services.design import briefs as design_briefs
from app.services.design import service as design
from app.services.topics.platforms import PLATFORM_LABELS, get_rules
from app.services.workflow import transition_post

P = PostStatus
# Copy can be fixed until the post is submitted for approval (a typo found
# during design shouldn't send the post back to drafting).
EDITABLE = (
    P.DRAFT,
    P.CONTENT_REVIEW,
    P.DESIGN_PENDING,
    P.DESIGN_IN_PROGRESS,
    P.DESIGN_UPLOADED,
    P.CHANGES_REQUESTED,
)
STATUS_GROUPS: dict[str, list[PostStatus] | None] = {
    "drafts": [P.DRAFT, P.CONTENT_REVIEW, P.CHANGES_REQUESTED],
    "design": [P.DESIGN_PENDING, P.DESIGN_IN_PROGRESS, P.DESIGN_UPLOADED],
    "approval": [P.PENDING_APPROVAL],
    "approved": [P.APPROVED, P.FINAL],
    "archived": [P.ARCHIVED, P.REJECTED],
    "all": None,
}
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


async def _get_post(db: AsyncSession, organization_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    post = await db.scalar(
        select(Post).where(Post.id == post_id, Post.organization_id == organization_id)
    )
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
    by_status = dict(
        (
            await db.execute(
                select(Post.status, func.count()).where(*filters).group_by(Post.status)
            )
        ).all()
    )
    counts = {
        group: sum(by_status.get(s, 0) for s in statuses) if statuses else sum(by_status.values())
        for group, statuses in STATUS_GROUPS.items()
    }
    if (statuses := STATUS_GROUPS[status]) is not None:
        filters.append(Post.status.in_(statuses))
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
    brief = await design.current_brief(db, post.id)
    await db.commit()  # keep seeded platform rules
    return PostDetail(
        **item.model_dump(),
        current=VersionRead.model_validate(current) if current else None,
        strategy=StrategyRead.model_validate(strategy) if strategy else None,
        variants=await _items(db, siblings),
        limits=Limits(max_length=rule.max_length, hashtag_limit=rule.hashtag_limit),
        editable=post.status in EDITABLE,
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


def _require_editable(post: Post) -> None:
    if post.status not in EDITABLE:
        raise InvalidStateTransition(
            "This post has moved on from drafting. Move it back to draft to change the copy.",
            details={"status": post.status.value},
        )


async def regenerate(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    instructions: str | None,
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    _require_editable(post)
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


# --- Editing ----------------------------------------------------------------------


async def update_post(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    data: dict[str, Any],
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    base = data.pop("base_version")
    note = data.pop("change_note", None)
    if "title" in data and data["title"] != post.title:
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
        _require_editable(post)
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
    await db.commit()
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
    _require_editable(post)
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
    "send-to-design": P.DESIGN_PENDING,
    "archive": P.ARCHIVED,
}


async def transition(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    action: str,
) -> PostDetail:
    post = await _get_post(db, organization_id, post_id)
    target = ACTIONS[action]
    if target == P.DESIGN_PENDING:
        if not post.current_version:
            raise InvalidStateTransition("Generate or write the post before moving it on.")
        if await generation.active_job(db, post.id):
            raise Conflict("This post is being generated. Wait for it to finish.")
    previous = post.status
    await transition_post(db, post, target, user_id=user_id)
    ai_brief = None
    if target == P.DESIGN_PENDING:
        brief = await design.open_brief(db, post, user_id)
        ai_brief = await design_briefs.start_ai_brief(db, brief)
    elif previous in DESIGN_STATUSES:
        await design.cancel_briefs(db, post)
    await db.commit()
    design_briefs.submit(ai_brief)
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
    post = await _get_post(db, organization_id, post_id)
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
