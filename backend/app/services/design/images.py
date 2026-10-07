"""AI images for design tasks: "Generate image with AI" turns the brief and
the post into an image, stored as the task's next creative version. The
creator then reviews it and submits it for approval like an upload."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.images import aspect_ratio, generate_image, get_image_provider
from app.ai.provider import AIError, AIErrorKind
from app.core.errors import AppError, Conflict, ErrorCode
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.ai import AIGenerationJob
from app.models.design import DesignBrief
from app.models.enums import JobStatus, Platform
from app.models.organization import BrandProfile
from app.models.post import Post, PostVersion
from app.schemas.design import TaskDetail
from app.services.design import service as design
from app.services.topics.platforms import PLATFORM_LABELS
from app.storage import get_storage
from app.workers.tasks import enqueue, schedule_retry

JOB_TYPE = "design_image"
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _now() -> datetime:
    return datetime.now(UTC)


async def active_job(db: AsyncSession, brief_id: uuid.UUID) -> AIGenerationJob | None:
    return await db.scalar(
        select(AIGenerationJob).where(
            AIGenerationJob.entity_id == brief_id,
            AIGenerationJob.type == JOB_TYPE,
            AIGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )


async def latest_job(db: AsyncSession, brief_id: uuid.UUID) -> AIGenerationJob | None:
    return await db.scalar(
        select(AIGenerationJob)
        .where(AIGenerationJob.entity_id == brief_id, AIGenerationJob.type == JOB_TYPE)
        .order_by(AIGenerationJob.created_at.desc())
        .limit(1)
    )


def image_prompt(
    brief: DesignBrief, post: Post, version: PostVersion | None, brand: BrandProfile | None
) -> str:
    """Everything the brief says, plus the post it illustrates."""
    platform = PLATFORM_LABELS[Platform(post.platform)]
    fmt = (brief.format or "single_image").replace("_", " ")
    # Image models weigh the start of the prompt most and garble small text:
    # lead with the scene, and allow exactly one line of text (the headline).
    lines = [
        f"A finished, professional {platform} visual ({fmt}"
        + (f", {brief.dimensions}" if brief.dimensions else "")
        + ")."
    ]
    if brief.visual_concept:
        lines.append(brief.visual_concept)
    if brief.format == "carousel":
        lines.append("This is the cover slide of a carousel.")
    if brief.visual_elements:
        lines.append("Include: " + "; ".join(brief.visual_elements) + ".")
    if brand:
        if brand.brand_colors:
            lines.append("Color palette: " + ", ".join(brand.brand_colors) + ".")
        if brand.tone:
            lines.append(f"Mood: {brand.tone}.")
        if brand.typography:
            lines.append(f"Typography: {brand.typography}.")
    if brief.headline:
        lines.append(
            "The only text in the image is this headline, large and spelled exactly: "
            f'"{brief.headline}". No other words, labels, captions or small print.'
        )
    else:
        lines.append("No text in the image.")
    # No other copy goes in: image models write out any text they're given.
    if not brief.visual_concept and version and version.hook:
        lines.append(f"Scene inspired by this idea (don't write it): {version.hook[:200]}")
    if brief.designer_notes:
        lines.append(f"Notes: {brief.designer_notes}")
    if brand and brand.forbidden_terms:
        lines.append("Never show these words: " + ", ".join(brand.forbidden_terms) + ".")
    lines.append(
        "Don't invent logos, watermarks or brand names; if a logo is wanted, leave clean "
        "space for it in a corner."
    )
    return "\n".join(lines)


async def start(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, role, task_id: uuid.UUID
) -> TaskDetail:
    """Queue one AI image for the task (one at a time)."""
    brief, _ = await design._workable(db, organization_id, user_id, role, task_id)
    adapter = get_image_provider()
    if adapter is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "AI images aren't set up. Ask your admin to add an image provider.",
        )
    if await active_job(db, brief.id):
        raise Conflict("An image is already being generated for this task.")
    job = AIGenerationJob(
        organization_id=organization_id,
        type=JOB_TYPE,
        entity_type="design_brief",
        entity_id=brief.id,
        provider=adapter.name,
        model=adapter.model,
        result={"requested_by": str(user_id)},
    )
    db.add(job)
    await db.commit()
    enqueue("design.image", job.id)
    return await design.task_detail(db, organization_id, brief.id)


def _image_error_message(exc: AIError) -> str:
    # Our own daily cap (llm_limits.json rpd); a provider's explanation wins.
    if exc.kind == AIErrorKind.QUOTA_EXHAUSTED and not exc.public:
        return (
            "Today's AI image allowance is used up. Upload a design instead, "
            "or generate one tomorrow."
        )
    return exc.user_message


async def run(job_id: uuid.UUID) -> None:
    """Execute one image job. Failures are recorded, never raised."""
    async with SessionLocal() as db:
        job = await db.get(AIGenerationJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return
        job.status, job.attempts = JobStatus.RUNNING, job.attempts + 1
        await db.commit()
        try:
            await _run(db, job)
            job.status = JobStatus.SUCCEEDED
        except AIError as exc:
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            if await schedule_retry(db, job, exc, "design.image"):
                return
            logger.warning("Design image job %s failed: %s", job_id, exc.message)
            job.status, job.error = JobStatus.FAILED, _image_error_message(exc)
            job.result = {**job.result, "error_kind": exc.kind.value}
        except Exception:
            logger.exception("Design image job %s crashed", job_id)
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            job.status, job.error = JobStatus.FAILED, "Image generation failed unexpectedly."
        job.completed_at = _now()
        await db.commit()


async def _run(db: AsyncSession, job: AIGenerationJob) -> None:
    brief = await db.get(DesignBrief, job.entity_id)
    post = await db.get(Post, brief.post_id) if brief else None
    if brief is None or post is None:
        raise AIError(AIErrorKind.BAD_REQUEST, "The design task no longer exists.", public=True)
    if brief.status not in design.ACTIVE or post.status not in design.UPLOADABLE:
        raise AIError(
            AIErrorKind.BAD_REQUEST, "The post isn't waiting for a design any more.", public=True
        )
    version = await db.scalar(
        select(PostVersion).where(
            PostVersion.post_id == post.id, PostVersion.version_number == post.current_version
        )
    )
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == brief.organization_id)
    )
    image = await generate_image(
        image_prompt(brief, post, version, brand),
        aspect_ratio(brief.dimensions),
        organization_id=brief.organization_id,
        job_id=job.id,
    )
    job.provider, job.model = image.provider, image.model
    extension = EXTENSIONS.get(image.mime_type, "png")
    key = f"{design._prefix(brief)}{uuid.uuid4().hex[:12]}-ai-image.{extension}"
    await get_storage().put(key, image.data, image.mime_type)
    requested_by = job.result.get("requested_by")
    number = await design.record_version(
        db,
        brief.organization_id,
        uuid.UUID(requested_by) if requested_by else None,
        brief,
        post,
        [(f"ai-image.{extension}", image.mime_type, len(image.data), key)],
        f"Generated with AI ({image.model})",
    )
    job.result = {**job.result, "version": number}
