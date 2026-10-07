"""Trend discovery job (spec §44, §46): collect → normalize → dedupe → score.

Every source runs in isolation: a missing key, timeout, rate limit, bad
payload or even a bug in one adapter is recorded as that source's result and
health, and the run continues with the others.
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.enums import DiscoveryRunStatus, SourceHealth
from app.models.trend import TrendDiscoveryRun, TrendSource
from app.services.knowledge.fetcher import Resolver, system_resolver
from app.services.trends import pipeline
from app.services.trends.inputs import load_org_inputs
from app.sources import SOURCES, get_source
from app.sources.base import RawTrendItem, SourceContext, SourceError, SourceErrorKind
from app.sources.base import TrendSource as Adapter
from app.workers.tasks import enqueue

LOOKBACK = timedelta(hours=48)
STALE_AFTER = timedelta(minutes=10)


def build_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": settings.trend_user_agent},
        follow_redirects=True,
    )


# Seams so tests can serve fake source APIs without network access.
http_client_factory: Callable[[Settings], httpx.AsyncClient] = build_client
resolver: Resolver = system_resolver

_HEALTH = {
    SourceErrorKind.RATE_LIMITED: SourceHealth.RATE_LIMITED,
    SourceErrorKind.AUTH: SourceHealth.DOWN,
    SourceErrorKind.UNAVAILABLE: SourceHealth.DEGRADED,
    SourceErrorKind.BAD_RESPONSE: SourceHealth.DEGRADED,
}


def _now() -> datetime:
    return datetime.now(UTC)


async def sync_source_registry() -> None:
    """Make sure every adapter has a health row (idempotent, run at startup)."""
    async with SessionLocal() as db:
        for source in SOURCES.values():
            await db.execute(
                insert(TrendSource)
                .values(id=uuid.uuid4(), key=source.key, name=source.name)
                .on_conflict_do_update(index_elements=["key"], set_={"name": source.name})
            )
        await db.commit()


async def _record_health(key: str, error: SourceError | None) -> None:
    async with SessionLocal() as db:
        values = (
            {"health": SourceHealth.HEALTHY, "last_success_at": _now(), "last_error": None}
            if error is None
            else {
                "health": _HEALTH.get(error.kind, SourceHealth.DEGRADED),
                "last_failure_at": _now(),
                "last_error": error.message[:1000],
            }
        )
        name = SOURCES[key].name if key in SOURCES else key
        await db.execute(
            insert(TrendSource)
            .values(id=uuid.uuid4(), key=key, name=name, **values)
            .on_conflict_do_update(index_elements=["key"], set_=values)
        )
        await db.commit()


async def _run_source(
    adapter: Adapter, ctx: SourceContext, time_limit: float
) -> tuple[str, list[RawTrendItem], SourceError | None, int]:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(time_limit):
            items = await adapter.collect(ctx)
        error = None
    except SourceError as exc:
        items, error = [], exc
    except TimeoutError:
        items = []
        error = SourceError(SourceErrorKind.UNAVAILABLE, f"No response within {int(time_limit)}s.")
    except Exception:  # a bug in one adapter must not stop the others
        logger.exception("Trend source %s crashed", adapter.key)
        items = []
        error = SourceError(SourceErrorKind.UNAVAILABLE, "Unexpected error in this source.")
    return adapter.key, items, error, int((time.perf_counter() - started) * 1000)


async def _finish(run_id: uuid.UUID, status: DiscoveryRunStatus, error: str | None = None) -> None:
    async with SessionLocal() as db:
        run = await db.get(TrendDiscoveryRun, run_id)
        if run is None:
            return
        run.status = status
        run.error = error
        run.finished_at = run.heartbeat_at = _now()
        await db.commit()


async def _discover(run_id: uuid.UUID) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        run = await db.get(TrendDiscoveryRun, run_id)
        assert run is not None
        org_inputs = await load_org_inputs(db, run.organization_id, run.locations or None)
        org_inputs_org_id = run.organization_id
        requested = list(run.sources)

    inputs, profile = org_inputs.inputs, org_inputs.profile
    results: dict[str, dict] = {}
    runnable: list[Adapter] = []
    for key in requested:
        adapter = get_source(key)
        if adapter is None:
            results[key] = {"status": "unknown", "items": 0, "error": "Unknown source."}
            continue
        config = adapter.configuration(settings, inputs)
        if not config.configured:
            missing = ", ".join(config.missing)
            results[key] = {
                "status": "not_configured",
                "items": 0,
                "error": f"Set {missing}." if missing else config.note,
            }
            continue
        results[key] = {"status": "running", "items": 0, "mode": config.mode}
        runnable.append(adapter)

    warnings = [f"Unrecognized market “{m}” was ignored." for m in org_inputs.unknown_markets]
    if not runnable:
        async with SessionLocal() as db:
            run = await db.get(TrendDiscoveryRun, run_id)
            assert run is not None
            run.results, run.warnings = results, warnings
            await db.commit()
        await _finish(
            run_id,
            DiscoveryRunStatus.FAILED,
            "None of the enabled sources are configured. See Trends › Sources.",
        )
        return

    async with http_client_factory(settings) as client:
        ctx = SourceContext(
            client=client,
            settings=settings,
            inputs=inputs,
            since=_now() - LOOKBACK,
            resolver=resolver,
        )
        outcomes = await asyncio.gather(
            *(_run_source(a, ctx, settings.trend_source_timeout_seconds) for a in runnable)
        )
        warnings += ctx.warnings

    items: dict[tuple[str, str], RawTrendItem] = {}
    for key, source_items, error, duration_ms in outcomes:
        await _record_health(key, error)
        results[key] = {
            **results[key],
            "status": "failed" if error else "ok",
            "items": len(source_items),
            "error": error.message if error else None,
            "error_kind": error.kind.value if error else None,
            "duration_ms": duration_ms,
        }
        for item in source_items:
            items[(item.source, item.source_item_id)] = item

    async with SessionLocal() as db:
        run = await db.get(TrendDiscoveryRun, run_id)
        assert run is not None
        run.results, run.warnings = results, warnings[:50]
        run.items_collected = len(items)
        run.heartbeat_at = _now()
        if items:
            stats = await pipeline.ingest(db, run.organization_id, list(items.values()), profile)
            run.trends_created = stats.trends_created
            run.trends_updated = stats.trends_updated
            run.mentions_created = stats.mentions_created
        await db.commit()

    failed = [k for k, _, error, _ in outcomes if error]
    if len(failed) == len(outcomes):
        reasons = "; ".join(f"{SOURCES[k].name}: {results[k]['error']}" for k in failed)
        await _finish(run_id, DiscoveryRunStatus.FAILED, f"All sources failed. {reasons}")
        return
    await _finish(run_id, DiscoveryRunStatus.SUCCEEDED)
    if settings.alignment_auto_analyze:
        # Organization alignment (spec §14) runs as its own job so slow AI
        # calls never hold the discovery run open.
        org_id = org_inputs_org_id
        enqueue("trends.align_organization", org_id)


async def run_discovery(run_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        run = await db.get(TrendDiscoveryRun, run_id)
        if run is None or run.status != DiscoveryRunStatus.QUEUED:
            return
        run.status = DiscoveryRunStatus.RUNNING
        run.started_at = run.heartbeat_at = _now()
        await db.commit()
    try:
        await _discover(run_id)
    except asyncio.CancelledError:
        await asyncio.shield(
            _finish(run_id, DiscoveryRunStatus.FAILED, "Interrupted: the server shut down.")
        )
        raise
    except Exception:
        logger.exception("Trend discovery run %s failed", run_id)
        await _finish(run_id, DiscoveryRunStatus.FAILED, "Discovery failed unexpectedly.")


def stale_condition():
    cutoff = _now() - STALE_AFTER
    return or_(
        TrendDiscoveryRun.heartbeat_at < cutoff,
        TrendDiscoveryRun.heartbeat_at.is_(None) & (TrendDiscoveryRun.created_at < cutoff),
    )


async def recover_stale_runs() -> int:
    async with SessionLocal() as db:
        result = await db.execute(
            update(TrendDiscoveryRun)
            .where(
                TrendDiscoveryRun.status.in_(
                    [DiscoveryRunStatus.QUEUED, DiscoveryRunStatus.RUNNING]
                ),
                stale_condition(),
            )
            .values(
                status=DiscoveryRunStatus.FAILED,
                error="Interrupted: the server restarted.",
                finished_at=_now(),
            )
        )
        await db.commit()
        return result.rowcount or 0
