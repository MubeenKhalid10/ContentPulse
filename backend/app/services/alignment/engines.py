"""Alignment engines: AI (RAG + LLM, spec §17-18) and rule-based fallback."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.embeddings import get_embedding_provider
from app.ai.gateway import LLMGateway
from app.ai.provider import AIError, AIErrorKind, StructuredResult
from app.core.config import get_settings
from app.models.enums import RelevanceLevel
from app.models.trend import Trend, TrendMention
from app.services.alignment.context import AlignmentContext
from app.services.alignment.result import (
    AlignmentResult,
    InvalidAlignment,
    Passage,
    parse_ai_output,
    response_schema,
)
from app.services.knowledge.search import search_knowledge
from app.services.trends.scoring import SOURCE_LABELS
from app.services.trends.text import keyword_matches, normalize_terms

MAX_PASSAGES = 6
MAX_MENTIONS = 8


async def retrieve_passages(
    db: AsyncSession, organization_id: uuid.UUID, trend: Trend
) -> list[Passage]:
    """Top knowledge chunks for this trend (spec §17)."""
    return await passages_for_query(
        db, organization_id, " ".join([trend.topic, *trend.keywords[:5]])
    )


async def passages_for_query(
    db: AsyncSession, organization_id: uuid.UUID, query: str, limit: int = MAX_PASSAGES
) -> list[Passage]:
    """Hybrid knowledge search, numbered K1, K2... for citation in prompts."""
    hits, _ = await search_knowledge(
        db,
        organization_id,
        query,
        limit=limit,
        provider=get_embedding_provider(),
        min_similarity=get_settings().knowledge_min_similarity,
    )
    return [
        Passage(
            ref=f"K{i}",
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            title=h.title,
            url=h.url,
            heading=h.heading,
            content=h.content,
            match=h.match,
        )
        for i, h in enumerate(hits, start=1)
    ]


async def top_mentions(db: AsyncSession, trend_id: uuid.UUID) -> list[TrendMention]:
    return list(
        await db.scalars(
            select(TrendMention)
            .where(TrendMention.trend_id == trend_id)
            .order_by(
                nulls_last(TrendMention.engagement.desc()),
                nulls_last(TrendMention.published_at.desc()),
            )
            .limit(MAX_MENTIONS)
        )
    )


def _hours_ago(when: datetime | None) -> str:
    if when is None:
        return "recently"
    hours = max(0, round((datetime.now(UTC) - when).total_seconds() / 3600))
    return f"{hours}h ago" if hours < 48 else f"{hours // 24}d ago"


def trend_prompt(trend: Trend, mentions: list[TrendMention], passages: list[Passage]) -> str:
    signals = "\n".join(
        f"- {key.replace('_', ' ')}: {value['score']} ({value['detail']})"
        for key, value in trend.signals.items()
        if key not in ("organization_fit", "audience_relevance")
    )
    coverage = "\n".join(
        f"- [{SOURCE_LABELS.get(m.source, m.source)}] {m.title}"
        + (f" ({m.author})" if m.author else "")
        + (f", {m.engagement_label}" if m.engagement_label else "")
        + f", {_hours_ago(m.published_at or m.detected_at)}"
        for m in mentions
    )
    if passages:
        knowledge = "\n".join(
            f'<passage id="{p.ref}" page="{p.title or p.url}" section="{p.heading or ""}">\n'
            f"{p.content}\n</passage>"
            for p in passages
        )
    else:
        knowledge = "(No passages in the organization's knowledge base match this trend.)"
    return (
        "<trend>\n"
        f"Topic: {trend.topic}\n"
        f"Related keywords: {', '.join(trend.keywords) or 'none'}\n"
        f"Seen in: {', '.join(trend.locations)}\n"
        f"Signals:\n{signals}\n"
        f"Recent coverage:\n{coverage}\n"
        "</trend>\n\n"
        f"<knowledge_passages>\n{knowledge}\n</knowledge_passages>\n\n"
        "Assess this trend for the organization."
    )


async def align_with_ai(
    provider: LLMGateway,
    ctx: AlignmentContext,
    trend: Trend,
    mentions: list[TrendMention],
    passages: list[Passage],
    *,
    job_id: uuid.UUID | None = None,
) -> tuple[AlignmentResult, StructuredResult]:
    prompt = prompts.load("organization_alignment")
    system = prompt.render(organization_name=ctx.name, organization_profile=ctx.profile_text)
    result = await provider.generate_structured(
        system=system,
        prompt=trend_prompt(trend, mentions, passages),
        schema=response_schema(ctx.platforms),
        max_tokens=8000,
        workflow="trend_alignment",
        organization_id=trend.organization_id,
        job_id=job_id,
        # Same trend, coverage, knowledge passages, profile and prompt version
        # give the same assessment: reuse it instead of spending a request.
        cache=True,
    )
    try:
        parsed = parse_ai_output(
            result.data, service_names=ctx.service_names, passages=passages, platforms=ctx.platforms
        )
    except InvalidAlignment as exc:
        raise AIError(AIErrorKind.BAD_OUTPUT, str(exc)) from exc
    return parsed, result


def _level(fit: int) -> RelevanceLevel:
    if fit >= 75:
        return RelevanceLevel.HIGHLY_RELEVANT
    if fit >= 45:
        return RelevanceLevel.RELEVANT
    if fit >= 20:
        return RelevanceLevel.WEAKLY_RELEVANT
    return RelevanceLevel.NOT_RELEVANT


def align_with_rules(
    ctx: AlignmentContext, trend: Trend, mentions: list[TrendMention], passages: list[Passage]
) -> AlignmentResult:
    """Transparent estimate when no LLM is configured: services named in the
    trend, knowledge passages about the topic, and tracked-keyword matches."""
    text = " ".join([trend.topic, *trend.keywords, *(m.title or "" for m in mentions)])
    services = keyword_matches(text, ctx.service_names)
    topic_terms = set(normalize_terms(trend.topic))
    supporting = [
        p for p in passages if topic_terms & set(normalize_terms(f"{p.heading or ''} {p.content}"))
    ]
    keyword_score = (trend.signals.get("keyword_match") or {}).get("score", 0)

    fit = 10
    reasons: list[str] = []
    if services:
        fit = max(fit, 85 if supporting else 75)
        reasons.append(f"The trend mentions your offering “{services[0]}”.")
    if supporting:
        fit = max(fit, min(80, 30 + 15 * len(supporting)))
        refs = ", ".join(f"[{p.ref}]" for p in supporting[:3])
        plural = len(supporting) != 1
        reasons.append(
            f"{len(supporting)} passage{'s' if plural else ''} in your knowledge base "
            f"discuss{'' if plural else 'es'} this topic {refs}."
        )
    if keyword_score >= 100:
        fit = max(fit, 60)
        reasons.append("It matches one of your tracked keywords.")
    elif keyword_score >= 35:
        fit = max(fit, 25)
    if not reasons:
        reasons.append("No connection found to your services, knowledge base or tracked keywords.")

    return AlignmentResult(
        engine="rules",
        classification=_level(fit),
        # Rule-based evidence is shallow: moderately sure when nothing connects,
        # less sure when something does (an LLM would judge the nuance).
        confidence=0.6 if fit <= 10 else 0.4,
        organization_fit=fit,
        audience_relevance=None,
        matched_services=services,
        reason=" ".join(reasons),
        evidence=[{"ref": p.ref, "supports": "Mentions the trend topic"} for p in supporting[:5]],
    )
