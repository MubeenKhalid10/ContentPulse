"""Admin CSV export: the organization's trends seen in the last seven days.

The window is captured once on the server, in UTC, as the half-open interval
[end - 7 days, end), and filters on `trends.last_seen_at`: a row is a trend
observed during the window, not necessarily first found in it. Times are shown
in the organization's timezone (its existing setting). Seven days are exactly
168 hours, so across a daylight-saving change the local start and end clock
times differ by an hour.

Source names come from `trend_mentions` (the same attribution the feed
uses), aggregated per trend in the query, so mentions never duplicate rows.
Raw provider payloads and descriptions are not exported.
"""

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.trend import Trend, TrendMention

WINDOW = timedelta(days=7)
# Used when the organization's timezone is not a known IANA name.
FALLBACK_TIMEZONE = "Asia/Karachi"

COLUMNS = (
    "Trend",
    "Category",
    "Keywords",
    "Sources",
    "Mentions",
    "Opportunity score",
    "Relevance",
    "Status",
    "First seen",
    "Last seen",
)

# A cell starting with one of these is a formula in Excel / Sheets / LibreOffice.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _now() -> datetime:
    return datetime.now(UTC)


def _zone(name: str | None) -> tuple[str, tzinfo]:
    for candidate in (name, FALLBACK_TIMEZONE):
        if not candidate:
            continue
        try:
            return candidate, ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return "UTC", UTC


@dataclass(frozen=True)
class ExportWindow:
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    timezone: str
    tz: tzinfo
    start: datetime  # inclusive, UTC
    end: datetime  # exclusive, UTC

    @property
    def local_start(self) -> datetime:
        return self.start.astimezone(self.tz)

    @property
    def local_end(self) -> datetime:
        return self.end.astimezone(self.tz)

    @property
    def filename(self) -> str:
        """ASCII only; the slug is [a-z0-9-] and the stamps carry the offset."""

        def stamp(value: datetime) -> str:
            return value.strftime("%Y%m%dT%H%M%S%z")

        return (
            f"contentpulse-trends_{self.organization_slug}_"
            f"{stamp(self.local_start)}_to_{stamp(self.local_end)}.csv"
        )


async def export_window(
    db: AsyncSession, organization_id: uuid.UUID, end: datetime | None = None
) -> ExportWindow:
    org = await db.get(Organization, organization_id)
    name, tz = _zone(org.timezone if org else None)
    end = (end or _now()).astimezone(UTC)
    return ExportWindow(
        organization_id=organization_id,
        organization_name=org.name if org else "",
        organization_slug=org.slug if org else "organization",
        timezone=name,
        tz=tz,
        start=end - WINDOW,
        end=end,
    )


def safe_cell(value: str) -> str:
    """Neutralise spreadsheet formulas in untrusted text (OWASP CSV
    injection): prefix a quote so the cell is shown as text. The stored
    value is unchanged."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


async def export_rows(db: AsyncSession, window: ExportWindow) -> list[list[str]]:
    # One row per trend: sources are aggregated in a tenant-scoped subquery.
    sources = (
        select(
            TrendMention.trend_id,
            func.array_agg(func.distinct(TrendMention.source)).label("sources"),
        )
        .where(TrendMention.organization_id == window.organization_id)
        .group_by(TrendMention.trend_id)
        .subquery()
    )
    rows = await db.execute(
        select(Trend, sources.c.sources)
        .outerjoin(sources, sources.c.trend_id == Trend.id)
        .where(
            Trend.organization_id == window.organization_id,
            Trend.last_seen_at >= window.start,
            Trend.last_seen_at < window.end,
        )
        .order_by(Trend.last_seen_at.desc(), Trend.id)
    )

    def when(value: datetime | None) -> str:
        return value.astimezone(window.tz).isoformat(timespec="seconds") if value else ""

    out = []
    for trend, names in rows:
        out.append(
            [
                safe_cell(trend.title or trend.topic),
                safe_cell(trend.category or ""),
                safe_cell(", ".join(trend.keywords or [])),
                safe_cell(", ".join(sorted(names or []))),
                str(trend.mention_count),
                "" if trend.opportunity_score is None else f"{trend.opportunity_score:.1f}",
                trend.relevance_level.value if trend.relevance_level else "",
                trend.status.value,
                when(trend.first_seen_at),
                when(trend.last_seen_at),
            ]
        )
    return out


def to_csv(rows: list[list[str]]) -> str:
    """RFC 4180 (quotes, commas and newlines escaped), with a UTF-8 BOM so
    spreadsheet apps read non-ASCII titles correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return "﻿" + buffer.getvalue()
