"""Design briefs (spec §27-28). A brief is built from the post the moment it's
sent to design, so the designer can start right away. When an LLM is
configured, a background job then rewrites the creative direction, unless a
person has edited the brief in the meantime.
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.provider import AIError, AIErrorKind, get_ai_provider
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.ai import AIGenerationJob
from app.models.design import DesignBrief
from app.models.enums import DesignBriefStatus, JobStatus, Platform
from app.models.organization import BrandProfile
from app.models.post import Post, PostVersion
from app.models.topic import ContentStrategy
from app.services.alignment.context import load_context
from app.services.content.copy import DESIGN_FORMATS
from app.services.topics.platforms import PLATFORM_LABELS
from app.workers.tasks import enqueue, schedule_retry

JOB_TYPE = "design_brief"
# Recommended canvas per platform and format.
DIMENSIONS: dict[tuple[Platform, str], str] = {
    (Platform.LINKEDIN, "carousel"): "1080×1350 (4:5), exported as PDF",
    (Platform.LINKEDIN, "single_image"): "1200×1200 (1:1)",
    (Platform.LINKEDIN, "infographic"): "1080×1350 (4:5)",
    (Platform.LINKEDIN, "video"): "1920×1080 (16:9)",
    (Platform.X, "single_image"): "1600×900 (16:9)",
    (Platform.X, "carousel"): "1080×1080 (1:1), up to 4 images",
    (Platform.X, "infographic"): "1080×1350 (4:5)",
    (Platform.X, "video"): "1920×1080 (16:9)",
    (Platform.INSTAGRAM, "carousel"): "1080×1350 (4:5), up to 10 slides",
    (Platform.INSTAGRAM, "single_image"): "1080×1350 (4:5)",
    (Platform.INSTAGRAM, "infographic"): "1080×1350 (4:5)",
    (Platform.INSTAGRAM, "reel"): "1080×1920 (9:16)",
    (Platform.INSTAGRAM, "video"): "1080×1920 (9:16)",
    (Platform.FACEBOOK, "single_image"): "1080×1080 (1:1)",
    (Platform.FACEBOOK, "carousel"): "1080×1080 (1:1)",
    (Platform.FACEBOOK, "infographic"): "1080×1350 (4:5)",
    (Platform.FACEBOOK, "video"): "1280×720 (16:9)",
    (Platform.FACEBOOK, "reel"): "1080×1920 (9:16)",
    # Blog: the featured image doubles as the Open Graph (social share) image.
    (Platform.BLOG, "single_image"): "1200×630 (1.91:1)",
    (Platform.BLOG, "infographic"): "1200×2400 (1:2)",
    (Platform.BLOG, "video"): "1920×1080 (16:9)",
}
# Post types that imply a format, when the post didn't record one.
TYPE_FORMATS = {
    "carousel": "carousel",
    "infographic": "infographic",
    "reel": "reel",
    "video": "video",
    "thread": "text_only",
}
SLIDE_LINE = re.compile(
    r"(?:^|\s)((?:Slide|Shot|Frame)\s*\d+\s*[:.\-–]\s*[^\n]+?)"
    r"(?=\s+(?:Slide|Shot|Frame)\s*\d+\s*[:.\-–]|$)",
    re.I | re.M,
)


def choose_format(design_format: str | None, post_type: str | None) -> str:
    if design_format in DESIGN_FORMATS:
        return design_format
    lowered = (post_type or "").lower()
    for word, fmt in TYPE_FORMATS.items():
        if word in lowered:
            return fmt
    return "single_image"


def dimensions(platform: Platform, fmt: str) -> str | None:
    return DIMENSIONS.get((platform, fmt))


def parse_slides(visual_concept: str | None) -> list[str]:
    if not visual_concept:
        return []
    return [m.strip().rstrip(".") + "." for m in SLIDE_LINE.findall(visual_concept)]


def first_sentences(text: str | None, limit: int = 220) -> str | None:
    if not text:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out = ""
    for sentence in sentences:
        if len(out) + len(sentence) > limit and out:
            break
        out = f"{out} {sentence}".strip()
    return out[:limit] or None


def brand_requirements(brand: BrandProfile | None) -> dict:
    """From the database, never from the model (spec rule 1)."""
    return {
        "colors": brand.brand_colors if brand else [],
        "typography": brand.typography if brand else None,
        "logo": True,
        "requirements": [
            "Organization logo",
            "Brand typography and colors",
            "Minimal text on the visual",
            "Strong visual hierarchy",
        ],
        "avoid_terms": brand.forbidden_terms if brand else [],
    }


def default_slides(fmt: str, headline: str | None, cta: str | None) -> list[str]:
    """The carousel outline from spec §28 when the post didn't describe slides."""
    if fmt != "carousel":
        return []
    return [
        f"Slide 1: Hook: {headline}" if headline else "Slide 1: Strong hook",
        "Slide 2: What changed",
        "Slide 3: Why it matters",
        "Slide 4: Business implications",
        "Slide 5: Practical takeaway",
        f"Slide 6: Call to action: {cta}" if cta else "Slide 6: Call to action",
    ]


async def build_brief(db: AsyncSession, post: Post) -> DesignBrief:
    version = await db.scalar(
        select(PostVersion).where(
            PostVersion.post_id == post.id, PostVersion.version_number == post.current_version
        )
    )
    strategy = (
        await db.get(ContentStrategy, post.content_strategy_id)
        if post.content_strategy_id
        else None
    )
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == post.organization_id)
    )
    meta = version.meta if version else {}
    fmt = choose_format(meta.get("design_format"), strategy.post_type if strategy else None)
    headline = (version.hook or "").strip()[:200] if version else None
    supporting = first_sentences(version.body if version else None)
    cta = version.cta if version else None
    visual = meta.get("visual_concept")
    if post.platform == Platform.BLOG:
        # A featured image carries the article title, not the introduction.
        seo = meta.get("blog") or {}
        headline = seo.get("seo_title") or post.title or headline
        supporting = seo.get("meta_description") or first_sentences(
            version.hook if version else None
        )
    return DesignBrief(
        organization_id=post.organization_id,
        post_id=post.id,
        format=fmt,
        dimensions=dimensions(Platform(post.platform), fmt),
        visual_concept=visual,
        headline=headline or None,
        supporting_text=supporting,
        slide_structure=parse_slides(visual) or default_slides(fmt, headline, cta),
        visual_elements=[],
        brand_requirements=brand_requirements(brand),
        cta=cta,
        source="rules",
    )


# --- AI rewrite ----------------------------------------------------------------------


def response_schema() -> dict:
    def text(description: str) -> dict:
        return {"type": "string", "description": description}

    fields = {
        "format": {"type": "string", "enum": DESIGN_FORMATS},
        "dimensions": text("Pixel size and aspect ratio."),
        "visual_concept": text("Look, mood and composition."),
        "headline": text("Main on-image headline."),
        "supporting_text": text("One short supporting line, or empty."),
        "slide_structure": {"type": "array", "items": {"type": "string"}},
        "visual_elements": {"type": "array", "items": {"type": "string"}},
        "designer_notes": text("Anything else the designer needs."),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }


def brief_prompt(
    post: Post, version: PostVersion | None, strategy: ContentStrategy | None, current: DesignBrief
) -> str:
    label = PLATFORM_LABELS[Platform(post.platform)]
    is_blog = post.platform == Platform.BLOG
    seo = (version.meta.get("blog") or {}) if version and is_blog else {}
    lines = [
        f"Platform: {label}",
        "Deliverable: the article's featured image, also used as its social share image"
        if is_blog
        else None,
        f"Article title: {seo['seo_title']}" if seo.get("seo_title") else None,
        f"Post type: {strategy.post_type}" if strategy else None,
        f"Suggested format: {current.format}",
        f"Suggested dimensions: {current.dimensions}" if current.dimensions else None,
        f"Writer's visual idea: {current.visual_concept}" if current.visual_concept else None,
    ]
    copy = "\n\n".join(
        x
        for x in (
            version.hook if version else None,
            version.body if version else None,
            version.cta if version else None,
        )
        if x
    )
    noun = "blog article" if is_blog else f"{label} post"
    return (
        "<post>\n" + "\n".join(x for x in lines if x) + f"\n\n{copy}\n</post>\n\n"
        f"Write the design brief for this {noun}."
    )


async def start_ai_brief(db: AsyncSession, brief: DesignBrief) -> AIGenerationJob | None:
    provider = get_ai_provider(workflow=JOB_TYPE)
    if provider is None:
        return None
    job = AIGenerationJob(
        organization_id=brief.organization_id,
        type=JOB_TYPE,
        entity_type="design_brief",
        entity_id=brief.id,
        provider=provider.name,
        model=provider.model,
    )
    db.add(job)
    await db.flush()
    return job


def submit(job: AIGenerationJob | None) -> None:
    """Run after the transaction that created the brief has committed."""
    if job is not None:
        enqueue("design.brief", job.id)


async def run_ai_brief(job_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        job = await db.get(AIGenerationJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return
        job.status, job.attempts = JobStatus.RUNNING, job.attempts + 1
        await db.commit()
        try:
            brief = await db.get(DesignBrief, job.entity_id)
            provider = get_ai_provider(workflow=JOB_TYPE)
            if brief is None or provider is None:
                raise AIError(AIErrorKind.NOT_CONFIGURED, "Nothing to do.", public=True)
            post = await db.get(Post, brief.post_id)
            assert post is not None
            version = await db.scalar(
                select(PostVersion).where(
                    PostVersion.post_id == post.id,
                    PostVersion.version_number == post.current_version,
                )
            )
            strategy = (
                await db.get(ContentStrategy, post.content_strategy_id)
                if post.content_strategy_id
                else None
            )
            prompt = prompts.load(JOB_TYPE)
            job.prompt_template_id = await prompts.register(db, prompt, provider.model)
            ctx = await load_context(db, post.organization_id)
            raw = await provider.generate_structured(
                system=prompt.render(
                    organization_name=ctx.name, organization_profile=ctx.profile_text
                ),
                prompt=brief_prompt(post, version, strategy, brief),
                schema=response_schema(),
                max_tokens=4000,
                workflow=JOB_TYPE,
                organization_id=post.organization_id,
                job_id=job.id,
            )
            data = raw.data
            job.provider, job.model, job.input_tokens, job.output_tokens = (
                raw.provider,
                raw.model,
                raw.input_tokens,
                raw.output_tokens,
            )
            await db.refresh(brief)
            editable = brief.status in (DesignBriefStatus.OPEN, DesignBriefStatus.ASSIGNED)
            if brief.source == "rules" and editable:  # never overwrite a person's edits
                fmt = data.get("format") if data.get("format") in DESIGN_FORMATS else brief.format
                brief.format = fmt
                brief.dimensions = str(data.get("dimensions") or "")[:40] or dimensions(
                    Platform(post.platform), fmt
                )
                for field in ("visual_concept", "headline", "supporting_text", "designer_notes"):
                    value = str(data.get(field) or "").strip()
                    if value:
                        setattr(brief, field, value[:4000])
                brief.slide_structure = [str(s)[:300] for s in data.get("slide_structure") or []][
                    :20
                ]
                brief.visual_elements = [str(s)[:200] for s in data.get("visual_elements") or []][
                    :20
                ]
                brief.source = "ai"
                job.result = {"applied": True}
            else:
                job.result = {"applied": False, "reason": "edited or already in progress"}
            job.status = JobStatus.SUCCEEDED
        except AIError as exc:
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            if await schedule_retry(db, job, exc, "design.brief"):
                return
            logger.warning("Design brief job %s failed: %s", job_id, exc.message)
            job.status, job.error = JobStatus.FAILED, exc.user_message
            job.result = {"error_kind": exc.kind.value}
        except Exception:
            logger.exception("Design brief job %s crashed", job_id)
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            job.status, job.error = JobStatus.FAILED, "Brief generation failed unexpectedly."
        job.completed_at = datetime.now(UTC)
        await db.commit()
