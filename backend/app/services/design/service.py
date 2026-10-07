"""Designer tasks (spec §30, §41): a design brief is the designer's task.

DESIGN_PENDING → (take/start) DESIGN_IN_PROGRESS → (upload) DESIGN_UPLOADED
→ (submit) PENDING_APPROVAL. Every upload is a new creative version; files
are never replaced.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.images import get_image_provider
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, Forbidden, InvalidStateTransition, NotFound
from app.core.permissions import Permission, has_permission
from app.models.ai import AIGenerationJob
from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import DesignBriefStatus, JobStatus, MemberStatus, PostStatus
from app.models.organization import BrandProfile, OrganizationMember
from app.models.post import Post, PostVersion
from app.models.topic import TopicCandidate
from app.models.user import User
from app.schemas.design import (
    BrandGuidelines,
    CreativeFile,
    CreativeVersion,
    ImageJob,
    Person,
    PostCopy,
    TaskDetail,
    TaskListItem,
    TaskPage,
    TaskPost,
)
from app.services import audit
from app.services.approvals import workflow as approvals
from app.services.audit import AuditAction
from app.services.design import briefs
from app.services.workflow import transition_post
from app.storage import ALLOWED_TYPES, get_storage, guess_type, safe_filename, storage_provider
from app.storage.s3 import StorageUnavailable

B = DesignBriefStatus
ACTIVE = (B.OPEN, B.ASSIGNED, B.IN_PROGRESS)
EDITABLE_BRIEF = (B.OPEN, B.ASSIGNED, B.IN_PROGRESS)
FILTERS: dict[str, list[DesignBriefStatus] | None] = {
    "todo": [B.OPEN, B.ASSIGNED, B.IN_PROGRESS],
    "submitted": [B.SUBMITTED],
    "done": [B.COMPLETED],
    "cancelled": [B.CANCELLED],
    "all": None,
}
# Post statuses in which a designer can still deliver files (Sprint 8 adds
# CHANGES_REQUESTED → back to design).
UPLOADABLE = (
    PostStatus.DESIGN_PENDING,
    PostStatus.DESIGN_IN_PROGRESS,
    PostStatus.DESIGN_UPLOADED,
    PostStatus.CHANGES_REQUESTED,
)


def _now() -> datetime:
    return datetime.now(UTC)


# --- Brief lifecycle (called from the content workflow) ---------------------------------


async def open_brief(db: AsyncSession, post: Post, user_id: uuid.UUID) -> DesignBrief:
    """A post was sent to design: create its brief (the designer's task).
    The previous designer of this post, if any, gets it again."""
    previous = await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post.id, DesignBrief.assignee_id.is_not(None))
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )
    brief = await briefs.build_brief(db, post)
    if previous is not None:
        brief.assignee_id, brief.assigned_at, brief.status = (
            previous.assignee_id,
            _now(),
            B.ASSIGNED,
        )
    db.add(brief)
    await db.flush()
    return brief


async def cancel_briefs(db: AsyncSession, post: Post) -> None:
    """The post left design (back to draft, archived): close its open task."""
    rows = await db.scalars(
        select(DesignBrief).where(DesignBrief.post_id == post.id, DesignBrief.status.in_(ACTIVE))
    )
    for brief in rows:
        brief.status = B.CANCELLED


async def current_brief(db: AsyncSession, post_id: uuid.UUID) -> DesignBrief | None:
    return await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post_id, DesignBrief.status != B.CANCELLED)
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )


# --- Reading -----------------------------------------------------------------------


def person(user: User | None) -> Person | None:
    return Person(id=user.id, name=user.full_name, email=user.email) if user else None


async def _get(db: AsyncSession, organization_id: uuid.UUID, task_id: uuid.UUID) -> DesignBrief:
    brief = await db.scalar(
        select(DesignBrief).where(
            DesignBrief.id == task_id, DesignBrief.organization_id == organization_id
        )
    )
    if brief is None:
        raise NotFound("Design task")
    return brief


async def _items(db: AsyncSession, rows: list[DesignBrief]) -> list[TaskListItem]:
    post_ids = {b.post_id for b in rows}
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
    user_ids = {b.assignee_id for b in rows if b.assignee_id}
    users = (
        {u.id: u for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )
    versions = (
        dict(
            (
                await db.execute(
                    select(CreativeAsset.post_id, func.count(func.distinct(CreativeAsset.version)))
                    .where(CreativeAsset.post_id.in_(post_ids))
                    .group_by(CreativeAsset.post_id)
                )
            ).all()
        )
        if post_ids
        else {}
    )
    items = []
    for b in rows:
        post = posts[b.post_id]
        items.append(
            TaskListItem(
                id=b.id,
                status=b.status,
                format=b.format,
                dimensions=b.dimensions,
                headline=b.headline,
                post=TaskPost(
                    id=post.id,
                    title=post.title,
                    platform=post.platform,
                    status=post.status,
                    current_version=post.current_version,
                    topic_title=topics.get(post.topic_id),
                ),
                assignee=person(users.get(b.assignee_id)),
                creative_versions=versions.get(post.id, 0),
                source=b.source,
                created_at=b.created_at,
                updated_at=b.updated_at,
                submitted_at=b.submitted_at,
            )
        )
    return items


async def list_tasks(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    status: str,
    mine: bool,
    platform: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> TaskPage:
    filters = [DesignBrief.organization_id == organization_id]
    if mine:
        filters.append(DesignBrief.assignee_id == user_id)
    if platform:
        on_platform = select(Post.id).where(
            Post.organization_id == organization_id, Post.platform == platform
        )
        filters.append(DesignBrief.post_id.in_(on_platform))
    if q:
        pattern = f"%{q.strip()}%"
        titled = select(Post.id).where(
            Post.organization_id == organization_id, Post.title.ilike(pattern)
        )
        filters.append(or_(DesignBrief.post_id.in_(titled), DesignBrief.headline.ilike(pattern)))
    by_status = dict(
        (
            await db.execute(
                select(DesignBrief.status, func.count())
                .where(*filters)
                .group_by(DesignBrief.status)
            )
        ).all()
    )
    counts = {
        name: sum(by_status.get(s, 0) for s in statuses) if statuses else sum(by_status.values())
        for name, statuses in FILTERS.items()
    }
    if (statuses := FILTERS[status]) is not None:
        filters.append(DesignBrief.status.in_(statuses))
    total = await db.scalar(select(func.count()).select_from(DesignBrief).where(*filters))
    order = (
        [DesignBrief.status != B.IN_PROGRESS, DesignBrief.created_at.desc()]
        if status == "todo"
        else [DesignBrief.updated_at.desc()]
    )
    rows = list(
        await db.scalars(
            select(DesignBrief)
            .where(*filters)
            .order_by(*order, DesignBrief.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return TaskPage(items=await _items(db, rows), total=total or 0, counts=counts)


async def creative_versions(db: AsyncSession, post_id: uuid.UUID) -> list[CreativeVersion]:
    assets = list(
        await db.scalars(
            select(CreativeAsset)
            .where(CreativeAsset.post_id == post_id)
            .order_by(CreativeAsset.version.desc(), CreativeAsset.position)
        )
    )
    uploader_ids = {a.uploaded_by for a in assets if a.uploaded_by}
    users = (
        {u.id: u for u in await db.scalars(select(User).where(User.id.in_(uploader_ids)))}
        if uploader_ids
        else {}
    )
    storage = get_storage()
    versions: dict[int, CreativeVersion] = {}
    for a in assets:
        group = versions.setdefault(
            a.version,
            CreativeVersion(
                version=a.version,
                note=a.note,
                uploaded_by=person(users.get(a.uploaded_by)),
                created_at=a.created_at,
                files=[],
            ),
        )
        group.files.append(
            CreativeFile(
                id=a.id,
                file_name=a.file_name,
                file_type=a.file_type,
                file_size=a.file_size,
                position=a.position,
                url=await storage.download_url(a.storage_key, a.file_name, inline=True),
                download_url=await storage.download_url(a.storage_key, a.file_name, inline=False),
            )
        )
    return list(versions.values())


async def task_detail(
    db: AsyncSession, organization_id: uuid.UUID, task_id: uuid.UUID
) -> TaskDetail:
    brief = await _get(db, organization_id, task_id)
    [item] = await _items(db, [brief])
    post = await db.get(Post, brief.post_id)
    assert post is not None
    version = await db.scalar(
        select(PostVersion).where(
            PostVersion.post_id == post.id, PostVersion.version_number == post.current_version
        )
    )
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == organization_id)
    )
    pending = await db.scalar(
        select(func.count()).where(
            AIGenerationJob.entity_id == brief.id,
            AIGenerationJob.type == briefs.JOB_TYPE,
            AIGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    settings = get_settings()
    return TaskDetail(
        **item.model_dump(),
        visual_concept=brief.visual_concept,
        supporting_text=brief.supporting_text,
        slide_structure=brief.slide_structure,
        visual_elements=brief.visual_elements,
        brand_requirements=brief.brand_requirements,
        cta=brief.cta,
        designer_notes=brief.designer_notes,
        content=PostCopy(
            version=version.version_number,
            hook=version.hook,
            body=version.body,
            cta=version.cta,
            hashtags=version.hashtags,
            blog=version.meta.get("blog"),
        )
        if version
        else None,
        brand=BrandGuidelines(
            brand_voice=brand.brand_voice if brand else None,
            tone=brand.tone if brand else None,
            colors=brand.brand_colors if brand else [],
            typography=brand.typography if brand else None,
            content_guidelines=brand.content_guidelines if brand else None,
            forbidden_terms=brand.forbidden_terms if brand else [],
        ),
        creatives=await creative_versions(db, post.id),
        storage=storage_provider(settings),
        max_upload_mb=settings.upload_max_mb,
        allowed_types=sorted(ALLOWED_TYPES),
        ai_brief_pending=bool(pending),
        ai_images=get_image_provider(settings) is not None,
        image_job=await _image_job(db, brief.id),
        review=await approvals.latest_review(db, post.id),
    )


async def _image_job(db: AsyncSession, brief_id: uuid.UUID) -> ImageJob | None:
    job = await db.scalar(
        select(AIGenerationJob)
        .where(AIGenerationJob.entity_id == brief_id, AIGenerationJob.type == "design_image")
        .order_by(AIGenerationJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        return None
    return ImageJob(status=job.status, error=job.error, version=(job.result or {}).get("version"))


# --- Actions -----------------------------------------------------------------------


def _record(
    db: AsyncSession,
    brief: DesignBrief,
    user_id: uuid.UUID,
    action: AuditAction,
    new: dict,
    old: dict | None = None,
) -> None:
    audit.record(
        db,
        organization_id=brief.organization_id,
        user_id=user_id,
        action=action,
        entity_type="design_brief",
        entity_id=brief.id,
        old_value=old,
        new_value=new,
    )


async def update_brief(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    changes: dict[str, Any],
) -> TaskDetail:
    brief = await _get(db, organization_id, task_id)
    if brief.status not in EDITABLE_BRIEF:
        raise InvalidStateTransition(
            "This brief can no longer be changed.", details={"status": brief.status.value}
        )
    for key in ("slide_structure", "visual_elements"):
        if key in changes and changes[key] is None:
            changes[key] = []
    old, new = audit.diff(brief, changes)
    if new:
        for field, value in changes.items():
            setattr(brief, field, value)
        brief.source = "edited"
        _record(db, brief, user_id, AuditAction.DESIGN_BRIEF_UPDATED, new, old)
    await db.commit()
    return await task_detail(db, organization_id, brief.id)


def _can_manage(role) -> bool:
    return has_permission(role, Permission.DESIGN_MANAGE)


async def assign(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role,
    task_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
) -> TaskDetail:
    brief = await _get(db, organization_id, task_id)
    if brief.status not in ACTIVE:
        raise InvalidStateTransition(
            "Only open tasks can be assigned.", details={"status": brief.status.value}
        )
    manager = _can_manage(role)
    if not manager:
        if assignee_id != user_id:
            raise Forbidden("You can only take tasks yourself. Ask an admin to assign others.")
        if brief.assignee_id not in (None, user_id):
            raise Forbidden("This task is already assigned to someone else.")
    if assignee_id is not None:
        member = await db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == assignee_id,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
        )
        if member is None or not has_permission(member.role, Permission.DESIGN_UPLOAD):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Assign the task to an active team member who can upload designs.",
                details=[
                    {"field": "assignee_id", "message": "Not a designer in this organization."}
                ],
            )
    old = {"assignee_id": brief.assignee_id}
    brief.assignee_id = assignee_id
    brief.assigned_at = _now() if assignee_id else None
    if brief.status != B.IN_PROGRESS:
        brief.status = B.ASSIGNED if assignee_id else B.OPEN
    _record(db, brief, user_id, AuditAction.DESIGN_TASK_ASSIGNED, {"assignee_id": assignee_id}, old)
    await db.commit()
    return await task_detail(db, organization_id, brief.id)


async def _workable(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, role, task_id: uuid.UUID
) -> tuple[DesignBrief, Post]:
    """A task the current user may deliver files for; claims it if unassigned.
    Any creator may deliver: the assignee shows who is on it, it doesn't lock
    others out (one role writes and designs)."""
    brief = await _get(db, organization_id, task_id)
    if brief.status not in ACTIVE:
        raise InvalidStateTransition("This task is closed.", details={"status": brief.status.value})
    post = await db.get(Post, brief.post_id)
    assert post is not None
    if post.status not in UPLOADABLE:
        raise InvalidStateTransition(
            "The post isn't waiting for a design.", details={"status": post.status.value}
        )
    if brief.assignee_id is None:
        brief.assignee_id, brief.assigned_at = user_id, _now()
    return brief, post


async def start(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, role, task_id: uuid.UUID
) -> TaskDetail:
    brief, post = await _workable(db, organization_id, user_id, role, task_id)
    brief.status = B.IN_PROGRESS
    if post.status == PostStatus.DESIGN_PENDING:
        await transition_post(db, post, PostStatus.DESIGN_IN_PROGRESS, user_id=user_id)
    await db.commit()
    return await task_detail(db, organization_id, brief.id)


def _prefix(brief: DesignBrief) -> str:
    return f"orgs/{brief.organization_id}/posts/{brief.post_id}/briefs/{brief.id}/"


def _file_error(message: str, field: str = "file") -> AppError:
    return AppError(
        ErrorCode.FILE_UPLOAD_FAILED, message, details=[{"field": field, "message": message}]
    )


def _content_type(file_name: str, declared: str) -> str:
    content_type = (declared or "").split(";")[0].strip().lower() or guess_type(file_name) or ""
    if content_type not in ALLOWED_TYPES:
        raise _file_error(
            f"“{file_name}” isn't a supported file. Upload images (PNG, JPG, WebP, GIF, "
            "SVG), PDFs or videos (MP4, MOV, WebM)."
        )
    return content_type


async def upload_ticket(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role,
    task_id: uuid.UUID,
    file_name: str,
    file_type: str,
    file_size: int,
):
    """Step 1 of the upload (spec §41): a signed URL the browser uploads to directly."""
    brief, _ = await _workable(db, organization_id, user_id, role, task_id)
    settings = get_settings()
    max_bytes = settings.upload_max_mb * 1_000_000
    if file_size > max_bytes:
        raise _file_error(f"“{file_name}” is larger than the {settings.upload_max_mb} MB limit.")
    content_type = _content_type(file_name, file_type)
    key = f"{_prefix(brief)}{uuid.uuid4().hex[:12]}-{safe_filename(file_name)}"
    await db.commit()  # keep an auto-assignment
    return await get_storage().upload_target(key, content_type, max_bytes)


async def register_assets(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role,
    task_id: uuid.UUID,
    files: list[dict],
    note: str | None,
) -> TaskDetail:
    """Step 2: the browser finished uploading. Verify each object really exists
    in storage under this task, then record the files as the next version."""
    brief, post = await _workable(db, organization_id, user_id, role, task_id)
    storage = get_storage()
    max_bytes = get_settings().upload_max_mb * 1_000_000
    checked = []
    for f in files:
        key = f["storage_key"]
        if not key.startswith(_prefix(brief)) or ".." in key:
            raise _file_error("That file wasn't uploaded for this task.", "storage_key")
        try:
            info = await storage.head(key)
        except StorageUnavailable as exc:
            raise AppError(
                ErrorCode.FILE_UPLOAD_FAILED, "File storage is unavailable. Try again shortly."
            ) from exc
        if info is None:
            raise _file_error(
                f"“{f['file_name']}” didn't finish uploading. Upload it again.", "storage_key"
            )
        if info.size > max_bytes:
            await storage.delete(key)
            raise _file_error(f"“{f['file_name']}” is larger than the upload limit.")
        checked.append((f, info, _content_type(f["file_name"], info.content_type or "")))
    files_in = [
        (f["file_name"], content_type, info.size, f["storage_key"])
        for f, info, content_type in checked
    ]
    await record_version(db, organization_id, user_id, brief, post, files_in, note)
    await db.commit()
    return await task_detail(db, organization_id, brief.id)


async def record_version(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    brief: DesignBrief,
    post: Post,
    files: list[tuple[str, str, int, str]],
    note: str | None,
) -> int:
    """Record stored files (name, type, size, key) as the post's next creative
    version and move the post to "design added". Caller commits."""
    version = (
        await db.scalar(
            select(func.max(CreativeAsset.version)).where(CreativeAsset.post_id == post.id)
        )
        or 0
    ) + 1
    for position, (file_name, content_type, size, key) in enumerate(files):
        db.add(
            CreativeAsset(
                organization_id=organization_id,
                post_id=post.id,
                design_brief_id=brief.id,
                file_name=file_name[:500],
                file_type=content_type,
                file_size=size,
                storage_key=key,
                storage_url=None,  # served through short-lived signed URLs only
                version=version,
                position=position,
                note=note,
                uploaded_by=user_id,
            )
        )
    await db.flush()
    brief.status = B.IN_PROGRESS
    if post.status != PostStatus.DESIGN_UPLOADED:
        await transition_post(db, post, PostStatus.DESIGN_UPLOADED, user_id=user_id)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.DESIGN_UPLOADED,
        entity_type="post",
        entity_id=post.id,
        new_value={"version": version, "files": len(files)},
    )
    return version


async def submit(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role,
    task_id: uuid.UUID,
    note: str | None = None,
) -> TaskDetail:
    """Spec §30: DESIGN_UPLOADED → PENDING_APPROVAL (also after a change
    request, re-submitting the latest creative). Refused without a creative."""
    brief = await _get(db, organization_id, task_id)
    if brief.status not in ACTIVE:
        raise InvalidStateTransition(
            "This task was already submitted or closed.", details={"status": brief.status.value}
        )
    if brief.assignee_id not in (None, user_id) and not _can_manage(role):
        raise Forbidden("This task is assigned to someone else.")
    post = await db.get(Post, brief.post_id)
    assert post is not None
    await approvals.submit_post(db, post, user_id, note)
    await db.commit()
    return await task_detail(db, organization_id, brief.id)
