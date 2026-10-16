"""Operational metrics for trend sources, appended to /health/metrics.

Process counters (requests, latency, cache events) come from this process;
the snapshot gauges (today's usage, remaining budget, cooldowns, run state)
are read from the database, so they are the same whichever process serves
them. Labels are provider keys, statuses and frequencies only: never
organization ids, queries, URLs or credentials.
"""

from datetime import UTC, datetime

from sqlalchemy import text

from app.ai.metrics import metrics
from app.core.config import get_settings


def record_request(source: str, outcome: str, seconds: float | None = None) -> None:
    metrics.inc("trend_provider_requests_total", source=source, outcome=outcome)
    if seconds is not None:
        metrics.observe("trend_provider_latency_seconds", seconds, source=source)


def _line(name: str, value: float, **labels: str) -> str:
    body = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{body}}} {value:g}" if body else f"{name} {value:g}"


def _header(name: str, kind: str, text_: str) -> list[str]:
    return [f"# HELP {name} {text_}", f"# TYPE {name} {kind}"]


async def snapshot() -> str:
    from app.db.session import SessionLocal
    from app.sources.provider_cache import cache_stats

    settings = get_settings()
    lines: list[str] = []

    lines += _header(
        "trend_provider_cache_events_total",
        "counter",
        "Provider cache events in this process (memory_hit, db_hit, miss, stored, ...).",
    )
    for source, events in cache_stats.snapshot().items():
        for event, count in events.items():
            lines.append(
                _line("trend_provider_cache_events_total", count, source=source, event=event)
            )

    async with SessionLocal() as db:
        today = datetime.now(UTC).date()
        usage = await db.execute(
            text(
                "SELECT source, reserved, completed, failed, over_budget FROM provider_usage "
                "WHERE usage_date = :day AND scope = '*' ORDER BY source"
            ),
            {"day": today},
        )
        lines += _header(
            "trend_provider_usage_today",
            "gauge",
            "Outbound requests today (UTC) per provider, all organizations.",
        )
        remaining: list[str] = []
        for source, reserved, completed, failed, over in usage:
            for field, value in (
                ("reserved", reserved),
                ("completed", completed),
                ("failed", failed),
                ("over_budget", over),
            ):
                lines.append(_line("trend_provider_usage_today", value, source=source, field=field))
            budget = settings.provider_daily_budgets.get(source)
            if budget is not None:
                remaining.append(
                    _line(
                        "trend_provider_budget_remaining", max(budget - reserved, 0), source=source
                    )
                )
        lines += _header(
            "trend_provider_budget_remaining",
            "gauge",
            "Requests left today under PROVIDER_DAILY_BUDGETS (providers with a budget).",
        )
        lines += remaining

        cooldowns = await db.execute(
            text(
                "SELECT key, extract(epoch FROM cooldown_until - now()) FROM trend_sources "
                "WHERE cooldown_until > now() ORDER BY key"
            )
        )
        lines += _header(
            "trend_provider_cooldown_seconds",
            "gauge",
            "Seconds until a paused provider may be called again.",
        )
        for source, seconds in cooldowns:
            lines.append(_line("trend_provider_cooldown_seconds", float(seconds), source=source))

        runs = await db.execute(
            text(
                "SELECT status, count(*) FROM trend_discovery_runs "
                "WHERE status IN ('queued', 'running') GROUP BY status"
            )
        )
        lines += _header(
            "trend_discovery_active_runs", "gauge", "Queued or running discovery runs."
        )
        for status, count in runs:
            lines.append(_line("trend_discovery_active_runs", count, status=status))

        frequencies = await db.execute(
            text(
                "SELECT trend_frequency, count(*) FROM organization_settings "
                "GROUP BY trend_frequency ORDER BY 1"
            )
        )
        lines += _header(
            "trend_organizations_by_frequency", "gauge", "Organizations per discovery frequency."
        )
        for frequency, count in frequencies:
            lines.append(_line("trend_organizations_by_frequency", count, frequency=frequency))
    return "\n".join(lines) + "\n"
