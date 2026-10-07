"""Content strategies (spec §21): the plan for one platform, before any copy."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.provider import AIError, AIErrorKind, get_ai_provider
from app.core.errors import AppError, ErrorCode, InvalidStateTransition, NotFound
from app.core.logging import logger
from app.models.ai import AIGenerationJob
from app.models.enums import JobStatus, Platform, StrategyStatus, TopicStatus
from app.models.organization import BrandProfile, OrganizationSettings
from app.models.topic import ContentStrategy, PlatformRule, TopicCandidate
from app.models.trend import Trend
from app.schemas.topic import StrategyRead, StrategySuggestion
from app.services import audit
from app.services.alignment.context import load_context
from app.services.audit import AuditAction
from app.services.content import blog
from app.services.topics.platforms import PLATFORM_LABELS, get_rules
from app.services.topics.service import get_topic
from app.services.workflow import STRATEGY_MACHINE

JOB_TYPE = "content_strategy"
LIMITS = {
    "post_type": 120,
    "objective": 120,
    "tone": 120,
    "recommended_format": 60,
}
TEXT_FIELDS = (
    "content_angle",
    "target_audience",
    "hook_direction",
    "cta_direction",
    "rationale",
)


def _validation(field: str, message: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR, message, details=[{"field": field, "message": message}]
    )


async def _enabled_platforms(db: AsyncSession, organization_id: uuid.UUID) -> list[Platform]:
    settings = await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )
    configured = settings.enabled_platforms if settings else []
    enabled = [Platform(p) for p in configured if p in Platform]
    return enabled or list(Platform)


async def _check_platform(
    db: AsyncSession, organization_id: uuid.UUID, platform: Platform
) -> PlatformRule:
    if platform not in await _enabled_platforms(db, organization_id):
        raise _validation(
            "platform",
            f"{PLATFORM_LABELS[platform]} isn't one of your organization's platforms. "
            "Enable it in Organization settings first.",
        )
    return (await get_rules(db, organization_id))[platform]


def _post_type(rule: PlatformRule, value: str) -> str:
    """Normalize to the playbook's spelling; reject types the playbook doesn't offer."""
    for option in rule.post_types:
        if option.casefold() == value.strip().casefold():
            return option
    raise _validation(
        "post_type",
        f"Choose a post type from the {PLATFORM_LABELS[rule.platform]} playbook: "
        f"{', '.join(rule.post_types)}.",
    )


def _details(platform: Platform, value: dict[str, Any] | None) -> dict[str, Any]:
    """Platform-specific plan; only Blog has one (its SEO plan)."""
    details = {k: v for k, v in (value or {}).items() if v not in (None, "", [])}
    if details and platform != Platform.BLOG:
        raise _validation(
            "details",
            f"SEO details only apply to Blog strategies, not {PLATFORM_LABELS[platform]}.",
        )
    return details


def _require_shortlisted(topic: TopicCandidate) -> None:
    if topic.status != TopicStatus.SHORTLISTED:
        raise InvalidStateTransition(
            "Shortlist this topic before planning content for it.",
            details={"status": topic.status.value},
        )


async def _get_strategy(
    db: AsyncSession, organization_id: uuid.UUID, topic_id: uuid.UUID, strategy_id: uuid.UUID
) -> ContentStrategy:
    strategy = await db.scalar(
        select(ContentStrategy).where(
            ContentStrategy.id == strategy_id,
            ContentStrategy.topic_id == topic_id,
            ContentStrategy.organization_id == organization_id,
        )
    )
    if strategy is None:
        raise NotFound("Strategy")
    return strategy


async def create_strategy(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    topic_id: uuid.UUID,
    data: dict[str, Any],
) -> StrategyRead:
    topic = await get_topic(db, organization_id, topic_id)
    _require_shortlisted(topic)
    platform = Platform(data["platform"])
    rule = await _check_platform(db, organization_id, platform)
    strategy = ContentStrategy(
        organization_id=organization_id,
        topic_id=topic.id,
        created_by=user_id,
        **{
            **data,
            "post_type": _post_type(rule, data["post_type"]),
            "details": _details(platform, data.get("details")),
        },
    )
    db.add(strategy)
    await db.flush()
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.STRATEGY_CREATED,
        entity_type="content_strategy",
        entity_id=strategy.id,
        new_value={
            "topic": topic.title,
            "platform": platform,
            "post_type": strategy.post_type,
            "source": strategy.source,
        },
    )
    await db.commit()
    await db.refresh(strategy)
    return StrategyRead.model_validate(strategy)


async def update_strategy(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    topic_id: uuid.UUID,
    strategy_id: uuid.UUID,
    changes: dict[str, Any],
) -> StrategyRead:
    strategy = await _get_strategy(db, organization_id, topic_id, strategy_id)
    if strategy.status != StrategyStatus.DRAFT:
        raise InvalidStateTransition(
            "Only draft strategies can be edited. Reopen it as a draft first.",
            details={"status": strategy.status.value},
        )
    platform = Platform(changes.get("platform", strategy.platform))
    if "platform" in changes or "post_type" in changes:
        rule = await _check_platform(db, organization_id, platform)
        changes["post_type"] = _post_type(rule, changes.get("post_type", strategy.post_type))
    if "platform" in changes or "details" in changes:
        # Switching platform drops a plan that only made sense for the old one.
        kept = strategy.details if platform == strategy.platform else {}
        changes["details"] = _details(platform, changes.get("details", kept))
    old, new = audit.diff(strategy, changes)
    for field, value in changes.items():
        setattr(strategy, field, value)
    if new:
        audit.record(
            db,
            organization_id=organization_id,
            user_id=user_id,
            action=AuditAction.STRATEGY_UPDATED,
            entity_type="content_strategy",
            entity_id=strategy.id,
            old_value=old,
            new_value=new,
        )
    await db.commit()
    await db.refresh(strategy)
    return StrategyRead.model_validate(strategy)


_ACTIONS = {
    StrategyStatus.APPROVED: AuditAction.STRATEGY_APPROVED,
    StrategyStatus.DRAFT: AuditAction.STRATEGY_REOPENED,
    StrategyStatus.ARCHIVED: AuditAction.STRATEGY_ARCHIVED,
}


async def transition_strategy(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    topic_id: uuid.UUID,
    strategy_id: uuid.UUID,
    target: StrategyStatus,
) -> StrategyRead:
    strategy = await _get_strategy(db, organization_id, topic_id, strategy_id)
    STRATEGY_MACHINE.assert_can(strategy.status, target)
    if target == StrategyStatus.APPROVED:
        _require_shortlisted(await get_topic(db, organization_id, topic_id))
        strategy.approved_by, strategy.approved_at = user_id, datetime.now(UTC)
    elif target == StrategyStatus.DRAFT:
        strategy.approved_by, strategy.approved_at = None, None
    previous = strategy.status
    strategy.status = target
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=_ACTIONS[target],
        entity_type="content_strategy",
        entity_id=strategy.id,
        old_value={"status": previous},
        new_value={"status": target, "platform": strategy.platform},
    )
    await db.commit()
    await db.refresh(strategy)
    return StrategyRead.model_validate(strategy)


# --- Suggestions --------------------------------------------------------------


def playbook_text(rule: PlatformRule) -> str:
    lines = [
        f"Post types: {', '.join(rule.post_types)}",
        f"Objectives: {', '.join(rule.objectives) or 'any'}",
        f"Tone: {rule.tone}" if rule.tone else None,
        f"Maximum length: {rule.max_length} characters" if rule.max_length else None,
        (f"Hashtags: at most {rule.hashtag_limit}" if rule.hashtag_limit else "Hashtags: none")
        if rule.hashtag_limit is not None
        else None,
        f"Guidance: {rule.guidance}" if rule.guidance else None,
    ]
    return "\n".join(line for line in lines if line)


def topic_prompt(
    topic: TopicCandidate, platform: Platform, keywords: list[str] | None = None
) -> str:
    angles = "\n".join(
        f"- {a.get('title', '')}: {a.get('angle', '')}"
        + (f" (suggested for {', '.join(a['platforms'])})" if a.get("platforms") else "")
        for a in topic.suggested_angles
    )
    fit = next((f for f in topic.platform_fit if f.get("platform") == platform.value), None)
    return (
        "<topic>\n"
        f"Title: {topic.title}\n"
        f"Summary: {topic.summary or 'n/a'}\n"
        f"Why it matters to the organization: {topic.relevance_reason or 'n/a'}\n"
        f"Related services: {', '.join(topic.matched_services) or 'none identified'}\n"
        f"Target audience: {topic.target_audience or 'see organization profile'}\n"
        f"Suggested angles:\n{angles or '- none yet'}\n"
        f"Claims to avoid: {'; '.join(topic.unsupported_claims) or 'none listed'}\n"
        + (f"Search keywords from the trend: {', '.join(keywords)}\n" if keywords else "")
        + (f"Why {PLATFORM_LABELS[platform]}: {'; '.join(fit['reasons'])}\n" if fit else "")
        + "</topic>\n\n"
        f"Plan this topic for {PLATFORM_LABELS[platform]}."
    )


def strategy_schema(rule: PlatformRule) -> dict[str, Any]:
    def text(description: str) -> dict[str, Any]:
        return {"type": "string", "description": description}

    objective: dict[str, Any] = (
        {"type": "string", "enum": rule.objectives}
        if rule.objectives
        else text("The business objective.")
    )
    fields = {
        "post_type": {"type": "string", "enum": rule.post_types},
        "objective": objective,
        "content_angle": text("The point of view the post takes, specific to the organization."),
        "target_audience": text("Who exactly the post is for."),
        "hook_direction": text("How the post should open to stop the scroll."),
        "cta_direction": text("What the reader should do next."),
        "tone": text("A few words describing the tone."),
        "recommended_format": text(
            "The concrete format, e.g. '6-slide educational carousel' (under 60 characters)."
        ),
        "rationale": text("Why this approach suits the topic, audience and platform."),
    }
    if rule.platform == Platform.BLOG:
        fields["details"] = blog.plan_schema()
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }


def _clean(rule: PlatformRule, data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, limit in LIMITS.items():
        value = str(data.get(field) or "").strip()
        out[field] = value[:limit] or None
    for field in TEXT_FIELDS:
        value = str(data.get(field) or "").strip()
        out[field] = value[:2000] or None
    try:
        out["post_type"] = _post_type(rule, out["post_type"] or "")
    except AppError as exc:
        message = "The AI chose a post type outside the playbook."
        raise AIError(AIErrorKind.BAD_OUTPUT, message) from exc
    if rule.platform == Platform.BLOG:
        out["details"] = blog.clean_plan(data.get("details"))
    return out


async def _rules_draft(
    db: AsyncSession, topic: TopicCandidate, rule: PlatformRule, platform: Platform
) -> dict[str, Any]:
    """A sensible starting point without an LLM: playbook + analysis + brand."""
    org_id = topic.organization_id
    settings = await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    brand = await db.scalar(select(BrandProfile).where(BrandProfile.organization_id == org_id))
    fit = next((f for f in topic.platform_fit if f.get("platform") == platform.value), None)
    post_type = (fit or {}).get("formats", [None])[0] or rule.post_types[0]

    goals = [g.casefold() for g in (settings.content_goals if settings else [])]
    objective = next(
        (o for o in rule.objectives if any(o.casefold() in g or g in o.casefold() for g in goals)),
        rule.objectives[0] if rule.objectives else None,
    )
    angle = next(
        (a for a in topic.suggested_angles if platform.value in (a.get("platforms") or [])),
        topic.suggested_angles[0] if topic.suggested_angles else None,
    )
    services = topic.matched_services
    audience = topic.target_audience or (settings.target_audience if settings else None)
    if angle:
        content_angle = f"{angle.get('title', '')}: {angle.get('angle', '')}".strip(": ")
    elif services:
        content_angle = (
            f"What {topic.title} means in practice, seen through your work on "
            f"{', '.join(services[:2])}."
        )
    else:
        content_angle = f"What {topic.title} means for {audience or 'your audience'}, and why now."
    cta = (
        brand.cta_guidelines.strip()
        if brand and brand.cta_guidelines
        else (
            f"Invite readers to learn how you approach {services[0]}."
            if services
            else "Ask readers how this affects them, to start a conversation."
        )
    )
    draft: dict[str, Any] = {
        "post_type": post_type,
        "objective": objective,
        "content_angle": content_angle,
        "target_audience": audience,
        "hook_direction": (
            f"Open with the most surprising or consequential fact about {topic.title}, "
            f"then say why it matters to {audience or 'the reader'}."
        ),
        "cta_direction": cta,
        "tone": ((brand.tone if brand and brand.tone else None) or rule.tone or "")[:120] or None,
        "recommended_format": post_type[:60],
        "rationale": (
            "; ".join(fit["reasons"]) + "."
            if fit and fit.get("reasons")
            else f"Built from the {PLATFORM_LABELS[platform]} playbook and the topic analysis."
        ),
    }
    if platform == Platform.BLOG:
        draft["details"] = blog.rules_plan(topic, await _trend_keywords(db, topic), audience)
    return draft


async def _trend_keywords(db: AsyncSession, topic: TopicCandidate) -> list[str]:
    trend = await db.get(Trend, topic.trend_id) if topic.trend_id else None
    return list(trend.keywords) if trend else []


async def suggest_strategy(
    db: AsyncSession,
    organization_id: uuid.UUID,
    topic_id: uuid.UUID,
    platform: Platform,
) -> StrategySuggestion:
    """Draft a strategy (not saved). Uses the LLM when configured and falls back
    to a rule-based draft if it's unavailable, so the button always works."""
    topic = await get_topic(db, organization_id, topic_id)
    _require_shortlisted(topic)
    rule = await _check_platform(db, organization_id, platform)
    provider = get_ai_provider(workflow=JOB_TYPE)
    notice: str | None = None
    if provider is not None:
        # Blog articles get their own strategist prompt (SEO plan, outline).
        prompt = prompts.load("blog_strategy" if platform == Platform.BLOG else JOB_TYPE)
        job = AIGenerationJob(
            organization_id=organization_id,
            type=JOB_TYPE,
            entity_type="topic",
            entity_id=topic.id,
            provider=provider.name,
            model=provider.model,
            status=JobStatus.RUNNING,
            attempts=1,
            prompt_template_id=await prompts.register(db, prompt, provider.model),
        )
        db.add(job)
        await db.commit()
        try:
            ctx = await load_context(db, organization_id)
            raw = await provider.generate_structured(
                system=prompt.render(
                    organization_name=ctx.name,
                    organization_profile=ctx.profile_text,
                    platform=PLATFORM_LABELS[platform],
                    platform_playbook=playbook_text(rule),
                ),
                prompt=topic_prompt(
                    topic,
                    platform,
                    await _trend_keywords(db, topic) if platform == Platform.BLOG else None,
                ),
                schema=strategy_schema(rule),
                max_tokens=4000,
                workflow=JOB_TYPE,
                organization_id=organization_id,
                job_id=job.id,
                interactive=True,
            )
            fields = _clean(rule, raw.data)
        except AIError as exc:
            logger.warning("Strategy suggestion for topic %s failed: %s", topic.id, exc.message)
            job.status, job.error = JobStatus.FAILED, exc.user_message
            job.result = {"error_kind": exc.kind.value, "platform": platform.value}
            notice = f"{exc.user_message} This is a rule-based draft instead."
        except Exception:
            logger.exception("Strategy suggestion for topic %s crashed", topic.id)
            job.status, job.error = JobStatus.FAILED, "Suggestion failed unexpectedly."
            notice = "The AI couldn't draft this, so this is a rule-based draft."
        else:
            job.status, job.provider, job.model = JobStatus.SUCCEEDED, raw.provider, raw.model
            job.input_tokens, job.output_tokens = raw.input_tokens, raw.output_tokens
            job.result = {"platform": platform.value, "post_type": fields["post_type"]}
            job.completed_at = datetime.now(UTC)
            await db.commit()
            return StrategySuggestion(platform=platform, source="ai", **fields)
        job.completed_at = datetime.now(UTC)
        await db.commit()
    fields = await _rules_draft(db, topic, rule, platform)
    return StrategySuggestion(platform=platform, source="rules", notice=notice, **fields)
