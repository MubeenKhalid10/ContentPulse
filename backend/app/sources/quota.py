"""Provider-wide request controls: daily budgets, cooldowns, Instagram hashtags.

Every outbound provider request (never a cache hit) passes through `guard`:

1. Cooldown: after a rate limit or exhausted quota, no request reaches that
   provider until `trend_sources.cooldown_until`, for any organization. A
   recent stored response is served instead when the provider may be cached.
2. Budget: one request is reserved atomically in `provider_usage` for the
   provider (scope "*") and the organization, against PROVIDER_DAILY_BUDGETS
   and PROVIDER_ORG_DAILY_BUDGETS. In monitor mode nothing is refused; the
   overrun is only counted and logged.
3. Outcome: the reservation is marked completed or failed; a rate limit
   starts (or extends) the cooldown, honoring Retry-After.

Accounting days are UTC. Every database step is its own short transaction,
never held across the provider request. If the database is unavailable the
request proceeds (monitoring is best effort) and the failure is logged.
"""

import hashlib
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import logger
from app.sources.cache_policy import source_of

GLOBAL_SCOPE = "*"
MAX_RETRY_AFTER = 86_400


def _source_error(kind: str, message: str):
    from app.sources.base import SourceError, SourceErrorKind

    return SourceError(SourceErrorKind(kind), message)


async def _execute(sql: str, **params: Any):
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        result = await db.execute(text(sql), params)
        await db.commit()
        return result


def utc_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(UTC).date()


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Seconds from a Retry-After header (delta-seconds or an HTTP date)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(min(int(value), MAX_RETRY_AFTER))
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return max(0.0, min(seconds, MAX_RETRY_AFTER))


def cooldown_seconds(
    *, status: int | None, retry_after: float | None, streak: int, now: datetime
) -> float:
    """How long to leave a provider alone after a rate-limit error."""
    settings = get_settings()
    if retry_after is not None:
        return retry_after
    if status == 402:
        # "Plan/daily usage limit reached": wait for the next UTC day.
        tomorrow = datetime.combine(utc_today(now) + timedelta(days=1), datetime.min.time(), UTC)
        return (tomorrow - now).total_seconds() + 300
    base = settings.provider_cooldown_base_seconds * 2 ** max(streak - 1, 0)
    delay = min(base, settings.provider_cooldown_max_seconds)
    return delay * (1 + random.uniform(0, 0.1))


# -- cooldowns ---------------------------------------------------------------


async def active_cooldown(source: str) -> datetime | None:
    result = await _execute(
        "SELECT cooldown_until FROM trend_sources WHERE key = :key AND cooldown_until > now()",
        key=source,
    )
    return result.scalar()


async def start_cooldown(source: str, *, status: int | None, retry_after: float | None) -> datetime:
    from app.sources import SOURCES

    now = datetime.now(UTC)
    result = await _execute("SELECT failure_streak FROM trend_sources WHERE key = :key", key=source)
    streak = (result.scalar() or 0) + 1
    seconds = cooldown_seconds(status=status, retry_after=retry_after, streak=streak, now=now)
    reason = "usage limit reached" if status == 402 else "rate limited"
    name = SOURCES[source].name if source in SOURCES else source
    # The end time is computed by the database: `active_cooldown` compares it
    # with the database's now(), and the API host's clock may differ from it.
    # Only ever extends a cooldown; concurrent workers can't shorten it.
    result = await _execute(
        """
        WITH c AS (SELECT now() + make_interval(secs => :seconds) AS until)
        INSERT INTO trend_sources (id, key, name, cooldown_until, cooldown_reason, failure_streak)
        SELECT gen_random_uuid(), :key, :name, c.until, :reason, 1 FROM c
        ON CONFLICT (key) DO UPDATE SET
          cooldown_until = GREATEST(
            coalesce(trend_sources.cooldown_until, excluded.cooldown_until),
            excluded.cooldown_until),
          cooldown_reason = :reason,
          failure_streak = trend_sources.failure_streak + 1
        RETURNING cooldown_until
        """,
        key=source,
        name=name,
        seconds=float(seconds),
        reason=reason,
    )
    until = result.scalar_one()
    logger.warning("%s %s: pausing requests until %s", name, reason, until.isoformat())
    return until


async def clear_failures(source: str) -> None:
    await _execute(
        "UPDATE trend_sources SET failure_streak = 0 WHERE key = :key AND failure_streak > 0",
        key=source,
    )


# -- budgets -----------------------------------------------------------------


@dataclass
class Reservation:
    source: str
    day: date
    scopes: list[str]


async def reserve(source: str, organization_id: str | None) -> Reservation:
    """Count one outbound request; refuse it in enforce mode when a budget is
    used up. Both scopes are reserved in one transaction (all or nothing)."""
    from app.db.session import SessionLocal

    settings = get_settings()
    enforce = settings.provider_budget_mode == "enforce"
    day = utc_today()
    limits = [(GLOBAL_SCOPE, settings.provider_daily_budgets.get(source))]
    if organization_id:
        limits.append((organization_id, settings.provider_org_daily_budgets.get(source)))
    over: list[str] = []
    async with SessionLocal() as db:
        for scope, limit in limits:
            reserved = (
                await db.execute(
                    text(
                        """
                        INSERT INTO provider_usage (source, usage_date, scope, reserved)
                        VALUES (:source, :day, :scope, 1)
                        ON CONFLICT (source, usage_date, scope) DO UPDATE
                          SET reserved = provider_usage.reserved + 1, updated_at = now()
                        RETURNING reserved
                        """
                    ),
                    {"source": source, "day": day, "scope": scope},
                )
            ).scalar_one()
            if limit is not None and reserved > limit:
                over.append("organization" if scope != GLOBAL_SCOPE else "platform")
        if over and enforce:
            await db.rollback()  # nothing counted: the request is not sent
            who = "this organization's" if over == ["organization"] else "the platform's"
            raise _source_error(
                "budget_exhausted",
                f"Skipped: {who} daily request budget for this provider is used up "
                "(resets at 00:00 UTC).",
            )
        if over:
            await db.execute(
                text(
                    "UPDATE provider_usage SET over_budget = over_budget + 1 "
                    "WHERE source = :source AND usage_date = :day AND scope = :scope"
                ),
                {"source": source, "day": day, "scope": GLOBAL_SCOPE},
            )
            logger.warning(
                "%s: over its daily request budget (%s); allowed in monitor mode",
                source,
                ", ".join(over),
            )
        await db.commit()
    return Reservation(source, day, [scope for scope, _ in limits])


async def finish(reservation: Reservation, outcome: str) -> None:
    """Record what happened: "completed", "failed", or "released" (the request
    was not sent after all, e.g. a hashtag over the weekly cap)."""
    if outcome == "released":
        update = "reserved = greatest(reserved - 1, 0)"
    else:
        column = "completed" if outcome == "completed" else "failed"
        update = f"{column} = {column} + 1"
    await _execute(
        f"UPDATE provider_usage SET {update}, updated_at = now() "
        "WHERE source = :source AND usage_date = :day AND scope = ANY(:scopes)",
        source=reservation.source,
        day=reservation.day,
        scopes=reservation.scopes,
    )


async def usage_today(source: str | None = None) -> list[dict]:
    """Provider-wide counters for today (operators' metrics; no organizations)."""
    rows = await _execute(
        "SELECT source, reserved, completed, failed, over_budget FROM provider_usage "
        "WHERE usage_date = :day AND scope = '*'" + (" AND source = :source" if source else ""),
        day=utc_today(),
        **({"source": source} if source else {}),
    )
    return [dict(r._mapping) for r in rows]


# -- the guard ---------------------------------------------------------------


async def guard[T](
    name: str,
    organization_id: str | None,
    call: Callable[[], Awaitable[T]],
    *,
    stale: Callable[[], Awaitable[T | None]] | None = None,
) -> T:
    """Run one outbound provider request under cooldown and budget control."""
    from app.sources.base import SourceError, SourceErrorKind
    from app.sources.observability import record_request

    source = source_of(name)
    if get_settings().provider_budget_mode == "off":
        return await _timed(source, call)
    try:
        until = await active_cooldown(source)
    except Exception:
        logger.warning("Provider cooldown check failed (%s)", source, exc_info=True)
        until = None
    if until is not None:
        if stale is not None and (cached := await stale()) is not None:
            record_request(source, "stale_served")
            return cached
        record_request(source, SourceErrorKind.COOLING_DOWN.value)
        raise SourceError(
            SourceErrorKind.COOLING_DOWN,
            f"Skipped: the provider asked us to slow down; paused until "
            f"{until.astimezone(UTC):%H:%M} UTC.",
        )
    try:
        reservation = await reserve(source, organization_id)
    except SourceError as exc:
        record_request(source, exc.kind.value)
        raise
    except Exception:
        logger.warning("Provider budget reservation failed (%s)", source, exc_info=True)
        reservation = None

    try:
        result = await _timed(source, call)
    except SourceError as exc:
        skipped = exc.kind in (SourceErrorKind.BUDGET_EXHAUSTED, SourceErrorKind.COOLING_DOWN)
        await _settle(reservation, "released" if skipped else "failed")
        if exc.kind == SourceErrorKind.RATE_LIMITED:
            try:
                await start_cooldown(source, status=exc.status, retry_after=exc.retry_after)
            except Exception:
                logger.warning("Could not record a cooldown (%s)", source, exc_info=True)
        raise
    except BaseException:
        await _settle(reservation, "failed")
        raise
    await _settle(reservation, "completed")
    try:
        await clear_failures(source)
    except Exception:
        pass
    return result


async def _timed[T](source: str, call: Callable[[], Awaitable[T]]) -> T:
    """Run the request, counting its outcome and duration."""
    from app.sources.base import SourceError
    from app.sources.observability import record_request

    started = time.perf_counter()
    try:
        result = await call()
    except SourceError as exc:
        record_request(source, exc.kind.value, time.perf_counter() - started)
        raise
    except Exception:
        record_request(source, "error", time.perf_counter() - started)
        raise
    record_request(source, "ok", time.perf_counter() - started)
    return result


async def _settle(reservation: Reservation | None, outcome: str) -> None:
    if reservation is None:
        return
    try:
        await finish(reservation, outcome)
    except Exception:
        logger.warning("Could not record a provider request outcome", exc_info=True)


# -- Instagram hashtags ------------------------------------------------------


def account_fingerprint(account_id: str | None) -> str:
    return hashlib.sha256((account_id or "").encode()).hexdigest()[:16]


async def hashtags_in_window(account_id: str | None) -> int:
    result = await _execute(
        "SELECT count(*) FROM instagram_hashtag_usage "
        "WHERE account = :account AND last_used_at > now() - interval '7 days'",
        account=account_fingerprint(account_id),
    )
    return int(result.scalar() or 0)


async def reserve_hashtag(account_id: str | None, hashtag: str) -> None:
    """Record a hashtag search for the account's rolling 7-day window.

    A hashtag already searched in the window uses no new slot. A new one is
    refused (enforce mode) once the cap is reached; in monitor mode it is
    recorded and the overrun logged. The check and insert run under a
    per-account transaction lock, so concurrent runs can't both take the last
    slot.
    """
    from app.db.session import SessionLocal

    settings = get_settings()
    if settings.provider_budget_mode == "off":
        return
    account = account_fingerprint(account_id)
    tag = hashtag.lower()[:100]
    async with SessionLocal() as db:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock))"), {"lock": f"ig:{account}"}
        )
        known = await db.scalar(
            text(
                "SELECT 1 FROM instagram_hashtag_usage WHERE account = :account "
                "AND hashtag = :tag AND last_used_at > now() - interval '7 days'"
            ),
            {"account": account, "tag": tag},
        )
        if not known:
            used = await db.scalar(
                text(
                    "SELECT count(*) FROM instagram_hashtag_usage WHERE account = :account "
                    "AND last_used_at > now() - interval '7 days'"
                ),
                {"account": account},
            )
            cap = settings.instagram_hashtag_weekly_cap
            if used >= cap:
                if settings.provider_budget_mode == "enforce":
                    await db.rollback()
                    raise _source_error(
                        "budget_exhausted",
                        f"Skipped #{tag}: {used} of {cap} unique hashtags already searched "
                        "in the last 7 days (Instagram's limit is 30 per account).",
                    )
                logger.warning("Instagram hashtag cap reached (%d/%d); monitor mode", used, cap)
        await db.execute(
            text(
                """
                INSERT INTO instagram_hashtag_usage (account, hashtag) VALUES (:account, :tag)
                ON CONFLICT (account, hashtag) DO UPDATE SET
                  last_used_at = now(),
                  first_used_at = CASE
                    WHEN instagram_hashtag_usage.last_used_at <= now() - interval '7 days'
                    THEN now() ELSE instagram_hashtag_usage.first_used_at END
                """
            ),
            {"account": account, "tag": tag},
        )
        await db.commit()


async def prune_hashtags() -> int:
    result = await _execute(
        "DELETE FROM instagram_hashtag_usage WHERE last_used_at < now() - interval '8 days'"
    )
    return result.rowcount or 0
