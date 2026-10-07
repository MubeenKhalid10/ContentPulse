"""Trend analysis pipeline (spec §14): normalize → deduplicate → score → store.

Raw items from all sources are clustered into canonical trends, matched to the
organization's existing trends, stored as mentions (one per source item, with
re-observations updating engagement and growth), and every recently active
trend is re-scored so freshness decays even when nothing new arrives.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trend import Trend, TrendMention
from app.services.trends.clustering import Cluster, cluster_items, similar_keys
from app.services.trends.scoring import MentionView, OrgProfile, most_common, score_trend
from app.sources.base import RawTrendItem

MATCH_WINDOW = timedelta(days=14)
SCORE_WINDOW = timedelta(days=7)


@dataclass
class IngestStats:
    trends_created: int = 0
    trends_updated: int = 0
    mentions_created: int = 0
    unclustered: int = 0


async def _upsert_mention(
    db: AsyncSession, org_id: uuid.UUID, trend_id: uuid.UUID, item: RawTrendItem, now: datetime
) -> bool:
    """Insert, or refresh engagement of an item seen before. Returns True if new."""
    stmt = insert(TrendMention).values(
        id=uuid.uuid4(),
        organization_id=org_id,
        trend_id=trend_id,
        source=item.source,
        source_item_id=item.source_item_id[:500],
        topic=(item.topic or item.title)[:300],
        title=item.title[:1000],
        description=item.description,
        keywords=item.keywords,
        category=item.category,
        location=item.location,
        source_url=item.source_url,
        author=(item.author or None) and item.author[:300],
        published_at=item.published_at,
        detected_at=now,
        last_seen_at=now,
        engagement=item.engagement,
        engagement_label=item.engagement_label,
        raw_data=item.raw_data,
    )
    existing = TrendMention.__table__.c
    hours_since = func.greatest(
        func.extract("epoch", now - func.coalesce(existing.last_seen_at, existing.detected_at))
        / 3600,
        0.25,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["organization_id", "source", "source_item_id"],
        set_={
            # Engagement change per hour between observations = real growth.
            "growth_indicator": func.coalesce(
                (stmt.excluded.engagement - existing.engagement) / hours_since,
                existing.growth_indicator,
            ),
            "engagement": func.coalesce(stmt.excluded.engagement, existing.engagement),
            "engagement_label": func.coalesce(
                stmt.excluded.engagement_label, existing.engagement_label
            ),
            "last_seen_at": now,
            "raw_data": stmt.excluded.raw_data,
        },
    ).returning(literal_column("(xmax = 0)"))
    return bool(await db.scalar(stmt))


def _find_match(cluster: Cluster, known: list[tuple[uuid.UUID, str]]) -> uuid.UUID | None:
    for trend_id, key in known:
        if key == cluster.key:
            return trend_id
    for trend_id, key in known:
        if similar_keys(key, cluster.key):
            return trend_id
    return None


async def ingest(
    db: AsyncSession, org_id: uuid.UUID, items: list[RawTrendItem], profile: OrgProfile
) -> IngestStats:
    now = datetime.now(UTC)
    stats = IngestStats()
    clusters, stats.unclustered = cluster_items(items, profile.tracked_keywords)

    known = list(
        (
            await db.execute(
                select(Trend.id, Trend.canonical_key).where(
                    Trend.organization_id == org_id, Trend.last_seen_at >= now - MATCH_WINDOW
                )
            )
        ).all()
    )

    for cluster in clusters:
        trend_id = _find_match(cluster, known)
        if trend_id is None:
            first_seen = min((i.published_at or now for i in cluster.items), default=now)
            trend = Trend(
                organization_id=org_id,
                canonical_key=cluster.key,
                topic=cluster.topic[:300],
                title=cluster.items[0].title[:500],
                description=next((i.description for i in cluster.items if i.description), None),
                keywords=cluster.keywords(),
                first_seen_at=min(first_seen, now),
                last_seen_at=now,
            )
            db.add(trend)
            await db.flush()
            trend_id = trend.id
            known.append((trend_id, cluster.key))
            stats.trends_created += 1
        else:
            trend = await db.get(Trend, trend_id)
            assert trend is not None
            trend.keywords = list(dict.fromkeys([*trend.keywords, *cluster.keywords()]))[:12]
            stats.trends_updated += 1
        for item in cluster.items:
            if await _upsert_mention(db, org_id, trend_id, item, now):
                stats.mentions_created += 1

    await db.flush()
    await rescore(db, org_id, profile, now)
    return stats


async def rescore(db: AsyncSession, org_id: uuid.UUID, profile: OrgProfile, now: datetime) -> int:
    """Refresh aggregates and scores of every recently active trend."""
    trends = list(
        await db.scalars(
            select(Trend).where(
                Trend.organization_id == org_id, Trend.last_seen_at >= now - SCORE_WINDOW
            )
        )
    )
    by_trend: dict[uuid.UUID, list[TrendMention]] = {}
    if trends:
        mentions = await db.scalars(
            select(TrendMention).where(TrendMention.trend_id.in_([t.id for t in trends]))
        )
        for mention in mentions:
            by_trend.setdefault(mention.trend_id, []).append(mention)
    for trend in trends:
        rows = by_trend.get(trend.id, [])
        if not rows:
            continue
        recent = [
            m for m in rows if (m.published_at or m.detected_at) >= now - SCORE_WINDOW
        ] or rows
        views = [
            MentionView(
                source=m.source,
                title=m.title,
                engagement=m.engagement,
                published_at=m.published_at,
                detected_at=m.detected_at,
                location=m.location,
                growth_indicator=m.growth_indicator,
            )
            for m in recent
        ]
        trend.mention_count = len(rows)
        trend.sources = sorted({m.source for m in rows})
        trend.locations = sorted({m.location or "GLOBAL" for m in rows})
        trend.category = most_common([m.category for m in rows]) or trend.category
        trend.last_seen_at = max(m.last_seen_at or m.detected_at for m in rows)
        trend.signals, trend.opportunity_score = score_trend(
            views,
            topic=trend.topic,
            keywords=trend.keywords,
            profile=profile,
            now=now,
            existing_signals=trend.signals,
        )
    return len(trends)
