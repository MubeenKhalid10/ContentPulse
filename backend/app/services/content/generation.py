"""Content generation (spec §23, §56): strategy + knowledge + brand + platform
rules → LLM → structured, validated post copy saved as a new version.

Generation runs in the background. Failures mark the job FAILED with the
reason and never touch existing versions, so the studio can offer a retry.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.gateway import LLMGateway
from app.ai.provider import AIError, AIErrorKind, get_ai_provider
from app.core.errors import Conflict
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.ai import AIGenerationJob
from app.models.enums import JobStatus, Platform, VersionSource
from app.models.organization import BrandProfile
from app.models.post import Post, PostVersion
from app.models.topic import ContentStrategy, PlatformRule, TopicCandidate
from app.models.trend import Trend
from app.services.alignment.context import load_context
from app.services.alignment.engines import passages_for_query, top_mentions
from app.services.alignment.result import Passage
from app.services.content import blog
from app.services.content.copy import (
    InvalidCopy,
    PostCopy,
    check_copy,
    parse_output,
    response_schema,
    template_copy,
)
from app.services.topics.platforms import PLATFORM_LABELS, get_rules
from app.services.topics.strategies import playbook_text
from app.workers.tasks import enqueue, schedule_retry

JOB_TYPE = "post_generation"
STALE_AFTER = timedelta(minutes=15)
KINDS = ("generate", "regenerate", "variant")


def _now() -> datetime:
    return datetime.now(UTC)


async def active_job(db: AsyncSession, post_id: uuid.UUID) -> AIGenerationJob | None:
    return await db.scalar(
        select(AIGenerationJob).where(
            AIGenerationJob.entity_id == post_id,
            AIGenerationJob.type == JOB_TYPE,
            AIGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            AIGenerationJob.created_at >= _now() - STALE_AFTER,
        )
    )


async def latest_jobs(
    db: AsyncSession, post_ids: list[uuid.UUID]
) -> dict[uuid.UUID, AIGenerationJob]:
    if not post_ids:
        return {}
    rows = await db.scalars(
        select(AIGenerationJob)
        .where(AIGenerationJob.entity_id.in_(post_ids), AIGenerationJob.type == JOB_TYPE)
        .order_by(AIGenerationJob.entity_id, AIGenerationJob.created_at.desc())
        .ext(distinct_on(AIGenerationJob.entity_id))
    )
    return {job.entity_id: job for job in rows if job.entity_id}


async def start(
    db: AsyncSession,
    post: Post,
    *,
    kind: str,
    user_id: uuid.UUID,
    instructions: str | None = None,
    source_post_id: uuid.UUID | None = None,
) -> AIGenerationJob:
    """Queue generation for `post` (one at a time per post) and commit."""
    assert kind in KINDS
    if await active_job(db, post.id):
        raise Conflict("This post is already being generated. Wait for it to finish.")
    provider = get_ai_provider(workflow=JOB_TYPE)
    job = AIGenerationJob(
        organization_id=post.organization_id,
        type=JOB_TYPE,
        entity_type="post",
        entity_id=post.id,
        provider=provider.name if provider else "template",
        model=provider.model if provider else None,
        result={
            "kind": kind,
            "requested_by": str(user_id),
            "instructions": instructions,
            "source_post_id": str(source_post_id) if source_post_id else None,
        },
    )
    db.add(job)
    await db.commit()
    enqueue("content.generate", job.id)
    return job


# --- Prompt -----------------------------------------------------------------------


def _line(label: str, value: str | None) -> str | None:
    return f"{label}: {value}" if value else None


def build_prompt(
    *,
    strategy: ContentStrategy,
    topic: TopicCandidate | None,
    coverage: list[str],
    passages: list[Passage],
    brand: BrandProfile | None,
    previous: PostVersion | None,
    kind: str,
    instructions: str | None,
) -> str:
    label = PLATFORM_LABELS[strategy.platform]
    is_blog = strategy.platform == Platform.BLOG
    noun = "blog article" if is_blog else f"{label} post"
    strategy_lines = [
        _line("Platform", label),
        _line("Post type", strategy.post_type),
        _line("Objective", strategy.objective),
        _line("Angle", strategy.content_angle),
        _line("Audience", strategy.target_audience),
        _line("Hook direction", strategy.hook_direction),
        _line("Call to action", strategy.cta_direction),
        _line("Tone", strategy.tone),
        _line("Format", strategy.recommended_format),
        *(blog.plan_lines(strategy.details) if is_blog else []),
    ]
    topic_lines = (
        [
            _line("Title", topic.title),
            _line("Summary", topic.summary),
            _line("Why it matters to the organization", topic.relevance_reason),
            _line("Related services", ", ".join(topic.matched_services)),
            _line("Claims to avoid", "; ".join(topic.unsupported_claims) or "none listed"),
        ]
        if topic
        else []
    )
    knowledge = (
        "\n".join(
            f'<passage id="{p.ref}" page="{p.title or p.url}" section="{p.heading or ""}">\n'
            f"{p.content}\n</passage>"
            for p in passages
        )
        or "(No matching passages in the organization's knowledge base. Make no specific "
        "claims about the organization beyond its profile.)"
    )
    vocabulary = [
        _line("Preferred terms", ", ".join(brand.preferred_terms)) if brand else None,
        _line("Forbidden terms", ", ".join(brand.forbidden_terms)) if brand else None,
        _line("Hashtag guidelines", brand.hashtag_guidelines) if brand else None,
    ]
    parts = [
        "<strategy>\n" + "\n".join(x for x in strategy_lines if x) + "\n</strategy>",
        "<topic>\n" + "\n".join(x for x in topic_lines if x) + "\n</topic>" if topic_lines else "",
        "<recent_coverage>\n" + "\n".join(f"- {c}" for c in coverage) + "\n</recent_coverage>"
        if coverage
        else "",
        f"<knowledge_passages>\n{knowledge}\n</knowledge_passages>",
        "<brand_vocabulary>\n" + "\n".join(x for x in vocabulary if x) + "\n</brand_vocabulary>"
        if any(vocabulary)
        else "",
    ]
    if previous is not None:
        seo = (previous.meta.get("blog") or {}) if is_blog else {}
        current = "\n\n".join(
            x
            for x in (
                _line("SEO title", seo.get("seo_title")),
                _line("Meta description", seo.get("meta_description")),
                _line("Keywords", ", ".join(seo.get("keywords") or [])),
                _line("Introduction" if is_blog else "Hook", previous.hook),
                _line("Body", previous.body),
                _line("Call to action", previous.cta),
                _line("Hashtags", " ".join(previous.hashtags)),
            )
            if x
        )
        parts.append(f"<existing_version>\n{current}\n</existing_version>")
    if kind == "variant":
        parts.append(
            f"Write an alternative {noun} for the same strategy: a clearly different hook "
            "and structure from the existing version, so the team can compare the two."
        )
    elif kind == "regenerate" and instructions:
        parts.append(
            f"<editor_instructions>\n{instructions}\n</editor_instructions>\n\n"
            f"Rewrite the {noun} following the editor's instructions. Keep what they "
            "didn't ask to change."
        )
    elif kind == "regenerate":
        parts.append(f"Write a fresh take on this {noun} with a different hook.")
    else:
        parts.append(f"Write the {noun}.")
    return "\n\n".join(p for p in parts if p)


# --- Execution --------------------------------------------------------------------


async def _generate_with_ai(
    provider: LLMGateway,
    db: AsyncSession,
    job: AIGenerationJob,
    post: Post,
    strategy: ContentStrategy,
    rule: PlatformRule,
    prompt_text: str,
    passages: list[Passage],
) -> PostCopy:
    prompt = prompts.load(f"{post.platform.value}_post")
    job.prompt_template_id = await prompts.register(db, prompt, provider.model)
    ctx = await load_context(db, post.organization_id)
    is_blog = post.platform == Platform.BLOG
    raw = await provider.generate_structured(
        system=prompt.render(
            organization_name=ctx.name,
            organization_profile=ctx.profile_text,
            platform_playbook=playbook_text(rule),
        ),
        prompt=prompt_text,
        schema=blog.response_schema() if is_blog else response_schema(),
        max_tokens=16000 if is_blog else 6000,
        workflow=JOB_TYPE,
        organization_id=post.organization_id,
        job_id=job.id,
    )
    job.provider, job.model = raw.provider, raw.model
    job.input_tokens, job.output_tokens = raw.input_tokens, raw.output_tokens
    refs = {p.ref for p in passages}
    try:
        if is_blog:
            return blog.parse_output(raw.data, refs=refs)
        return parse_output(raw.data, refs=refs, hashtag_limit=rule.hashtag_limit)
    except InvalidCopy as exc:
        raise AIError(AIErrorKind.BAD_OUTPUT, str(exc)) from exc


async def run(job_id: uuid.UUID) -> None:
    """Execute one generation job. Failures are recorded, never raised."""
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
            if await schedule_retry(db, job, exc, "content.generate"):
                return
            logger.warning("Post generation job %s failed: %s", job_id, exc.message)
            job.status, job.error = JobStatus.FAILED, exc.user_message
            job.result = {**job.result, "error_kind": exc.kind.value}
        except Exception:
            logger.exception("Post generation job %s crashed", job_id)
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            job.status, job.error = JobStatus.FAILED, "Generation failed unexpectedly."
        job.completed_at = _now()
        await db.commit()


async def _run(db: AsyncSession, job: AIGenerationJob) -> None:
    post = await db.get(Post, job.entity_id)
    if post is None:
        raise AIError(AIErrorKind.BAD_REQUEST, "The post no longer exists.", public=True)
    strategy = (
        await db.get(ContentStrategy, post.content_strategy_id)
        if post.content_strategy_id
        else None
    )
    if strategy is None:
        raise AIError(
            AIErrorKind.BAD_REQUEST, "The post's content strategy was deleted.", public=True
        )
    topic = await db.get(TopicCandidate, post.topic_id) if post.topic_id else None
    trend = await db.get(Trend, topic.trend_id) if topic and topic.trend_id else None
    rule = (await get_rules(db, post.organization_id))[Platform(post.platform)]
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == post.organization_id)
    )
    kind = job.result.get("kind", "generate")
    previous: PostVersion | None = None
    source_id = job.result.get("source_post_id")
    compare_to = uuid.UUID(source_id) if kind == "variant" and source_id else post.id
    compare_post = await db.get(Post, compare_to)
    if kind != "generate" and compare_post and compare_post.current_version:
        previous = await db.scalar(
            select(PostVersion).where(
                PostVersion.post_id == compare_post.id,
                PostVersion.version_number == compare_post.current_version,
            )
        )

    query = " ".join(x for x in (topic.title if topic else post.title, strategy.content_angle) if x)
    passages = await passages_for_query(db, post.organization_id, query)
    coverage = [m.title for m in await top_mentions(db, trend.id)][:8] if trend else []

    provider = get_ai_provider(workflow=JOB_TYPE)
    meta: dict = {"kind": kind, "strategy_id": str(strategy.id)}
    if provider is not None:
        prompt_text = build_prompt(
            strategy=strategy,
            topic=topic,
            coverage=coverage,
            passages=passages,
            brand=brand,
            previous=previous,
            kind=kind,
            instructions=job.result.get("instructions"),
        )
        copy = await _generate_with_ai(
            provider, db, job, post, strategy, rule, prompt_text, passages
        )
        prompt = prompts.load(f"{post.platform.value}_post")
        meta |= {
            "engine": "ai",
            "model": job.model,
            "prompt": {"name": prompt.name, "version": prompt.version},
        }
    elif post.platform == Platform.BLOG:
        copy = blog.template_copy(
            topic_title=topic.title if topic else (post.title or "This topic"),
            relevance_reason=topic.relevance_reason if topic else None,
            content_angle=strategy.content_angle,
            audience=strategy.target_audience,
            cta_direction=strategy.cta_direction,
            keywords=trend.keywords if trend else [],
            plan=strategy.details,
        )
        meta["engine"] = "template"
    else:
        copy = template_copy(
            topic_title=topic.title if topic else (post.title or "This topic"),
            relevance_reason=topic.relevance_reason if topic else None,
            content_angle=strategy.content_angle,
            audience=strategy.target_audience,
            cta_direction=strategy.cta_direction,
            keywords=trend.keywords if trend else [],
            hashtag_limit=rule.hashtag_limit,
        )
        meta["engine"] = "template"

    cited = set(copy.evidence)
    meta |= {
        "visual_concept": copy.visual_concept,
        "design_format": copy.design_format,
        "evidence": copy.evidence,
        "passages": [p.to_json() for p in sorted(passages, key=lambda p: p.ref not in cited)],
        "corrections": copy.corrections,
        "warnings": check_copy(
            hook=copy.hook,
            body=copy.body,
            cta=copy.cta,
            hashtags=copy.hashtags,
            forbidden_terms=brand.forbidden_terms if brand else [],
            max_length=rule.max_length,
            hashtag_limit=rule.hashtag_limit,
            platform_label=PLATFORM_LABELS[post.platform],
        ),
    }
    if copy.blog is not None:
        meta["blog"] = copy.blog
        meta["warnings"] += blog.check_blog(copy.blog, copy.hook, copy.body)
    if job.result.get("instructions"):
        meta["instructions"] = job.result["instructions"]

    number = post.current_version + 1
    db.add(
        PostVersion(
            organization_id=post.organization_id,
            post_id=post.id,
            version_number=number,
            hook=copy.hook,
            body=copy.body,
            cta=copy.cta,
            hashtags=copy.hashtags,
            mentions=[],
            meta=meta,
            source=VersionSource.AI,
            change_note={
                "generate": "Generated",
                "regenerate": "Regenerated"
                + (" with instructions" if meta.get("instructions") else ""),
                "variant": "Generated as a variant",
            }[kind],
            ai_generation_job_id=job.id,
            created_by=uuid.UUID(job.result["requested_by"])
            if job.result.get("requested_by")
            else None,
        )
    )
    post.current_version = number
    job.result = {**job.result, "version": number}
