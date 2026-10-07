"""Explainable trend scoring (spec §13).

Each signal is a 0-100 score with a plain-language `detail` so the UI can show
*why* a trend ranks where it does. The opportunity score is a weighted mean of
the signals that are available; audience relevance and organization fit are
filled in by AI alignment (Sprint 4) and are left empty until then.
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from app.services.trends.text import keyword_matches, normalize_terms
from app.sources.base import compact_number
from app.sources.locations import name_for

# Engagement that counts as "very high" (score 100) per source.
ENGAGEMENT_REFERENCE = {
    "google_trends": 1_000_000,  # searches
    "hacker_news": 1_000,  # points
    "reddit": 50_000,  # upvotes
    "x": 100_000,  # interactions
    "instagram": 200_000,  # likes + comments
}
ARTICLE_SOURCES = {"google_news", "newsapi", "gnews", "world_news", "newsdata", "rss"}
SOURCE_LABELS = {
    "google_trends": "Google Trends",
    "google_news": "Google News",
    "hacker_news": "Hacker News",
    "reddit": "Reddit",
    "rss": "RSS feeds",
    "newsapi": "NewsAPI",
    "gnews": "GNews",
    "x": "X",
    "instagram": "Instagram",
}
WEIGHTS = {
    "popularity": 0.25,
    "growth": 0.20,
    "freshness": 0.15,
    "location_relevance": 0.15,
    "source_diversity": 0.10,
    "keyword_match": 0.15,
    # Filled by AI alignment in Sprint 4; weights apply once present.
    "audience_relevance": 0.15,
    "organization_fit": 0.30,
}


@dataclass
class MentionView:
    source: str
    title: str | None
    engagement: int | None
    published_at: datetime | None
    detected_at: datetime
    location: str | None
    growth_indicator: float | None


@dataclass
class OrgProfile:
    markets: set[str]  # ISO codes; {"GLOBAL"} or empty means worldwide
    tracked_keywords: list[str]
    service_names: list[str]


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _log_score(value: float, reference: float) -> int:
    if value <= 0:
        return 0
    return _clamp(100 * math.log10(1 + value) / math.log10(1 + reference))


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _age_hours(m: MentionView, now: datetime) -> float:
    when = m.published_at or m.detected_at
    return max(0.0, (now - when).total_seconds() / 3600)


def popularity(mentions: list[MentionView]) -> dict:
    by_source: dict[str, list[MentionView]] = {}
    for m in mentions:
        by_source.setdefault(m.source, []).append(m)
    parts: list[tuple[int, str]] = []
    for source, items in by_source.items():
        if source in ENGAGEMENT_REFERENCE:
            peak = max((m.engagement or 0) for m in items)
            if peak:
                unit = "searches" if source == "google_trends" else "engagement"
                parts.append(
                    (
                        _log_score(peak, ENGAGEMENT_REFERENCE[source]),
                        f"{compact_number(peak)} {unit} on {_label(source)}",
                    )
                )
                continue
        count = len(items)
        noun = "article" if source in ARTICLE_SOURCES else "post"
        parts.append(
            (
                _clamp(20 + 15 * (count - 1)),
                f"{count} {noun}{'s' if count != 1 else ''} on {_label(source)}",
            )
        )
    parts.sort(reverse=True)
    score = parts[0][0] + 5 * (len(parts) - 1)
    return {"score": _clamp(score), "detail": "; ".join(d for _, d in parts[:3])}


def growth(mentions: list[MentionView], now: datetime) -> dict:
    candidates: list[tuple[int, str]] = []
    if any(m.source == "google_trends" for m in mentions):
        candidates.append((70, "Rising search on Google Trends right now"))
    for m in mentions:
        reference = ENGAGEMENT_REFERENCE.get(m.source)
        if not reference:
            continue
        if m.growth_indicator and m.growth_indicator > 0:
            per_hour = m.growth_indicator
            candidates.append(
                (
                    _log_score(per_hour, reference / 24),
                    f"Engagement up {compact_number(int(per_hour))}/hour since last check "
                    f"on {_label(m.source)}",
                )
            )
        if m.engagement:
            velocity = m.engagement / (_age_hours(m, now) + 2)
            candidates.append(
                (
                    _log_score(velocity, reference / 12),
                    f"{compact_number(int(velocity))} engagement/hour on {_label(m.source)}",
                )
            )
    recent = sum(1 for m in mentions if _age_hours(m, now) <= 24)
    if len(mentions) >= 2:
        share = recent / len(mentions)
        candidates.append(
            (
                _clamp(share * 60 + min(40, 8 * recent)),
                f"{recent} of {len(mentions)} mentions in the last 24 hours",
            )
        )
    if not candidates:
        return {"score": 20, "detail": "Single recent mention; growth unknown yet"}
    return dict(zip(("score", "detail"), max(candidates), strict=True))


def freshness(mentions: list[MentionView], now: datetime) -> dict:
    age = min(_age_hours(m, now) for m in mentions)
    score = 100 if age <= 3 else _clamp(100 * (1 - (age - 3) / 69))
    if age < 1:
        detail = "Latest mention under an hour ago"
    elif age < 48:
        hours = round(age)
        detail = f"Latest mention {hours} hour{'s' if hours != 1 else ''} ago"
    else:
        detail = f"Latest mention {round(age / 24)} days ago"
    return {"score": score, "detail": detail}


def location_relevance(mentions: list[MentionView], profile: OrgProfile) -> dict:
    markets = profile.markets - {"GLOBAL"}
    seen = {m.location or "GLOBAL" for m in mentions}
    if not markets:
        return {"score": 100, "detail": "You target a global audience"}
    hits = seen & markets
    if hits:
        names = ", ".join(sorted(name_for(c) for c in hits))
        return {"score": 100, "detail": f"Trending in {names}"}
    if "GLOBAL" in seen:
        return {"score": 60, "detail": "Global coverage, not market-specific"}
    names = ", ".join(sorted(name_for(c) for c in seen))
    return {"score": 15, "detail": f"Only seen in {names}, outside your markets"}


def source_diversity(mentions: list[MentionView]) -> dict:
    sources = sorted({m.source for m in mentions})
    score = {1: 25, 2: 55, 3: 80}.get(len(sources), 100)
    return {"score": score, "detail": f"Seen on {', '.join(_label(s) for s in sources)}"}


def keyword_match(text: str, profile: OrgProfile) -> dict:
    """Lexical stand-in for organization fit until AI alignment (Sprint 4)."""
    tracked = keyword_matches(text, profile.tracked_keywords)
    if tracked:
        return {"score": 100, "detail": f"Matches tracked keyword “{tracked[0]}”"}
    services = keyword_matches(text, profile.service_names)
    if services:
        return {"score": 90, "detail": f"Mentions your offering “{services[0]}”"}
    org_terms = {
        t for k in [*profile.tracked_keywords, *profile.service_names] for t in normalize_terms(k)
    }
    overlap = sorted(org_terms & set(normalize_terms(text)))
    if len(overlap) >= 2:
        return {"score": 60, "detail": f"Shares terms with your focus: {', '.join(overlap[:3])}"}
    if overlap:
        return {"score": 35, "detail": f"Shares the term “{overlap[0]}” with your focus"}
    if not org_terms:
        return {"score": 0, "detail": "Add tracked keywords and services to measure fit"}
    return {"score": 0, "detail": "No overlap with your keywords or services"}


def score_trend(
    mentions: list[MentionView],
    *,
    topic: str,
    keywords: list[str],
    profile: OrgProfile,
    now: datetime,
    existing_signals: dict | None = None,
) -> tuple[dict, float | None]:
    if not mentions:
        return existing_signals or {}, None
    text = " ".join([topic, *keywords, *(m.title or "" for m in mentions[:20])])
    signals = {
        "popularity": popularity(mentions),
        "growth": growth(mentions, now),
        "freshness": freshness(mentions, now),
        "location_relevance": location_relevance(mentions, profile),
        "source_diversity": source_diversity(mentions),
        "keyword_match": keyword_match(text, profile),
    }
    # Keep AI-derived signals (Sprint 4) across re-scoring.
    for key in ("audience_relevance", "organization_fit"):
        if existing_signals and existing_signals.get(key):
            signals[key] = existing_signals[key]
    return signals, opportunity(signals)


def opportunity(signals: dict) -> float | None:
    """Weighted mean of the signals present (AI signals join once analyzed)."""
    present = {k: v for k, v in signals.items() if k in WEIGHTS and v}
    if not present:
        return None
    total_weight = sum(WEIGHTS[k] for k in present)
    return round(sum(WEIGHTS[k] * v["score"] for k, v in present.items()) / total_weight, 1)


def most_common(values: list[str | None]) -> str | None:
    counts = Counter(v for v in values if v)
    return counts.most_common(1)[0][0] if counts else None
