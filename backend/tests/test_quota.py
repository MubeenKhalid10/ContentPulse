"""Provider budgets, cooldowns, skipped-source statuses and the Instagram
hashtag ledger."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.config import Settings, get_settings
from app.models.provider import InstagramHashtagUse, ProviderUsage
from app.models.trend import TrendSource
from app.sources import bookkeeping, quota
from app.sources.base import SourceError, SourceErrorKind
from tests.test_provider_cache import ALL_KEYS, run_source
from tests.test_trends_api import API, discover, internet, setup  # noqa: F401
from tests.trend_fixtures import FakeInternet


@pytest.fixture
def mode(monkeypatch):
    settings = get_settings()

    def set_mode(value: str, **overrides):
        monkeypatch.setattr(settings, "provider_budget_mode", value)
        for name, val in overrides.items():
            monkeypatch.setattr(settings, name, val)

    return set_mode


async def usage(db, source, scope="*"):
    row = await db.scalar(
        select(ProviderUsage).where(ProviderUsage.source == source, ProviderUsage.scope == scope)
    )
    if row is not None:
        await db.refresh(row)
    return row


async def ok() -> str:
    return "ok"


# --- Budgets --------------------------------------------------------------------------


async def test_monitor_mode_counts_but_never_refuses(db, mode):
    mode("monitor", provider_daily_budgets={"gnews": 2})
    for _ in range(4):
        assert await quota.guard("gnews", "org-a", ok) == "ok"
    row = await usage(db, "gnews")
    assert (row.reserved, row.completed, row.failed, row.over_budget) == (4, 4, 0, 2)
    assert (await usage(db, "gnews", "org-a")).reserved == 4


async def test_enforce_mode_refuses_over_budget(db, mode):
    mode("enforce", provider_daily_budgets={"gnews": 2})
    assert await quota.guard("gnews", None, ok) == "ok"
    assert await quota.guard("gnews", None, ok) == "ok"
    with pytest.raises(SourceError) as exc:
        await quota.guard("gnews", None, ok)
    assert exc.value.kind == SourceErrorKind.BUDGET_EXHAUSTED
    assert "00:00 UTC" in exc.value.message
    assert (await usage(db, "gnews")).reserved == 2  # the refused one isn't counted


async def test_concurrent_workers_cannot_overshoot_a_budget(db, mode):
    mode("enforce", provider_daily_budgets={"newsdata": 5})

    async def attempt():
        try:
            return await quota.guard("newsdata", None, ok)
        except SourceError as exc:
            return exc.kind

    results = await asyncio.gather(*(attempt() for _ in range(12)))
    assert results.count("ok") == 5
    assert results.count(SourceErrorKind.BUDGET_EXHAUSTED) == 7
    assert (await usage(db, "newsdata")).reserved == 5


async def test_per_organization_fair_share(db, mode):
    mode(
        "enforce",
        provider_daily_budgets={"exa": 10},
        provider_org_daily_budgets={"exa": 2},
    )
    for _ in range(2):
        await quota.guard("exa", "org-a", ok)
    with pytest.raises(SourceError) as exc:
        await quota.guard("exa", "org-a", ok)
    assert "this organization's" in exc.value.message
    # Another organization still has its own share of the provider budget.
    assert await quota.guard("exa", "org-b", ok) == "ok"
    assert (await usage(db, "exa")).reserved == 3


async def test_failures_and_cache_hits_are_accounted(db, mode):
    mode("monitor")

    async def boom():
        raise SourceError(SourceErrorKind.UNAVAILABLE, "down")

    with pytest.raises(SourceError):
        await quota.guard("gnews", None, boom)
    row = await usage(db, "gnews")
    assert (row.reserved, row.completed, row.failed) == (1, 0, 1)

    # Two identical requests: one provider call; the cache hit isn't counted.
    settings = Settings(_env_file=None, gnews_api_key="k")
    net = FakeInternet()
    await run_source("gnews", settings=settings, net=net)
    calls = len(net.calls)
    await run_source("gnews", settings=settings, net=net)
    assert len(net.calls) == calls
    assert (await usage(db, "gnews")).reserved == 1 + calls


async def test_off_mode_touches_nothing(db, mode):
    mode("off", provider_daily_budgets={"gnews": 0})
    assert await quota.guard("gnews", None, ok) == "ok"
    assert await usage(db, "gnews") is None


# --- Cooldowns ------------------------------------------------------------------------


def test_retry_after_parsing():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert quota.parse_retry_after("120") == 120
    assert quota.parse_retry_after("Wed, 14 Oct 2026 12:05:00 GMT", now) == 300
    assert quota.parse_retry_after("999999") == quota.MAX_RETRY_AFTER
    assert quota.parse_retry_after("soon") is None and quota.parse_retry_after(None) is None


def test_backoff_doubles_with_jitter_and_402_waits_for_tomorrow():
    now = datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    first = quota.cooldown_seconds(status=429, retry_after=None, streak=1, now=now)
    third = quota.cooldown_seconds(status=429, retry_after=None, streak=3, now=now)
    assert 60 <= first <= 66 and 240 <= third <= 264
    capped = quota.cooldown_seconds(status=429, retry_after=None, streak=20, now=now)
    assert capped <= 3600 * 1.1
    assert quota.cooldown_seconds(status=429, retry_after=30, streak=5, now=now) == 30
    # Daily plan limit: until just after midnight UTC.
    assert quota.cooldown_seconds(status=402, retry_after=None, streak=1, now=now) == 2 * 3600 + 300


async def test_rate_limit_pauses_the_provider_for_everyone(db, mode):
    mode("monitor")
    net = FakeInternet()
    net.failures["gnews.io"] = httpx.Response(429, headers={"Retry-After": "600"})
    settings = Settings(_env_file=None, gnews_api_key="k")
    with pytest.raises(SourceError) as exc:
        await run_source("gnews", settings=settings, net=net)
    assert exc.value.kind == SourceErrorKind.RATE_LIMITED
    # Measured on the database clock, which set the cooldown and enforces it.
    remaining = float(
        await db.scalar(
            select(func.extract("epoch", TrendSource.cooldown_until - func.now())).where(
                TrendSource.key == "gnews"
            )
        )
    )
    row = await db.scalar(select(TrendSource).where(TrendSource.key == "gnews"))
    assert 590 < remaining <= 600 and row.failure_streak == 1

    calls = len(net.calls)
    with pytest.raises(SourceError) as exc:
        await run_source("gnews", settings=settings, keywords=["other"], net=net)
    assert exc.value.kind == SourceErrorKind.COOLING_DOWN
    assert len(net.calls) == calls  # nothing was sent during the cooldown


async def test_cooldown_serves_a_recent_stored_copy_when_allowed(db, mode, monkeypatch):
    from app.models.provider import ProviderCache
    from app.sources.base import request_cache
    from tests.test_provider_cache import trends_request  # noqa: F401

    mode("monitor")
    monkeypatch.setattr(get_settings(), "provider_cache_backend", "postgres")
    monkeypatch.setattr(get_settings(), "provider_cache_persist_sources", ["google_trends"])
    first, _ = await run_source("google_trends")
    await db.execute(
        update(ProviderCache).values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    await db.commit()
    await quota.start_cooldown("google_trends", status=429, retry_after=600)
    request_cache.clear()
    second, net = await run_source("google_trends")
    assert net.calls == [] and [i.title for i in second] == [i.title for i in first]
    row = await db.scalar(select(ProviderCache))
    await db.refresh(row)
    assert row.expires_at < datetime.now(UTC)  # the stale copy wasn't re-stored as fresh


async def test_cooldowns_follow_the_database_clock(db, mode, monkeypatch):
    # The API host's clock may run ahead of the database's: a cooldown that
    # has already ended must not stay active, nor one be stretched.
    class Ahead(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(minutes=5)

    mode("monitor")
    monkeypatch.setattr(quota, "datetime", Ahead)
    await quota.start_cooldown("hacker_news", status=429, retry_after=0)
    assert await quota.active_cooldown("hacker_news") is None
    await quota.start_cooldown("hacker_news", status=429, retry_after=60)
    remaining = float(
        await db.scalar(
            select(func.extract("epoch", TrendSource.cooldown_until - func.now())).where(
                TrendSource.key == "hacker_news"
            )
        )
    )
    assert 50 < remaining <= 60


async def test_success_resets_the_backoff_streak(db, mode):
    mode("monitor")
    await quota.start_cooldown("hacker_news", status=429, retry_after=0)
    await quota.start_cooldown("hacker_news", status=429, retry_after=0)
    assert await quota.guard("hacker_news", None, ok) == "ok"
    row = await db.scalar(select(TrendSource).where(TrendSource.key == "hacker_news"))
    await db.refresh(row)
    assert row.failure_streak == 0


async def test_a_discovery_run_keeps_bookkeeping_off_the_request_path(db, mode, monkeypatch):
    # Inside a run the outcome writes happen beside the request and are all
    # recorded by the time the run's bookkeeping is drained; the cooldown is
    # read once per source rather than once per request.
    mode("monitor")
    reads = 0
    real_cooldown = quota.active_cooldown

    async def counted(source):
        nonlocal reads
        reads += 1
        return await real_cooldown(source)

    monkeypatch.setattr(quota, "active_cooldown", counted)
    async with bookkeeping.deferring():
        assert (
            await asyncio.gather(*(quota.guard("gnews", "org-a", ok) for _ in range(3)))
            == ["ok"] * 3
        )
        assert await quota.guard("gnews", "org-a", ok) == "ok"
    row = await usage(db, "gnews")
    assert (row.reserved, row.completed) == (4, 4)
    assert reads <= 3  # the concurrent first calls may each read; later ones don't

    async def limited():
        raise SourceError(SourceErrorKind.RATE_LIMITED, "slow down", status=429, retry_after=600)

    async with bookkeeping.deferring():
        with pytest.raises(SourceError):
            await quota.guard("gnews", None, limited)
        with pytest.raises(SourceError) as exc:  # this run sees its own cooldown at once
            await quota.guard("gnews", None, ok)
        assert exc.value.kind == SourceErrorKind.COOLING_DOWN


async def test_skipped_sources_are_reported_as_such(client, internet, db, mode):  # noqa: F811
    mode("enforce", provider_daily_budgets={"hacker_news": 0})
    admin, _ = await setup(client)
    await quota.start_cooldown("google_news", status=429, retry_after=3600)
    run = await discover(admin)
    assert run["status"] == "succeeded"
    results = run["results"]
    assert results["hacker_news"]["status"] == "budget_exhausted"
    assert results["google_news"]["status"] == "cooling_down"
    assert results["google_trends"]["status"] == "ok"
    # A deliberate skip doesn't mark the provider unhealthy.
    health = {s.key: s for s in await db.scalars(select(TrendSource))}
    assert "hacker_news" not in health or health["hacker_news"].health != "degraded"
    sources = {s["key"]: s for s in (await admin.get(f"{API}/sources")).json()}
    assert sources["google_news"]["cooldown_until"] is not None


async def test_only_skips_means_a_clear_failed_run(client, internet, mode, monkeypatch):  # noqa: F811
    mode("enforce")
    for key in ("google_trends", "google_news", "hacker_news", "reddit"):
        await quota.start_cooldown(key, status=429, retry_after=3600)
    admin, _ = await setup(client)
    run = await discover(admin, sources=["google_trends", "google_news", "hacker_news", "reddit"])
    assert run["status"] == "failed"
    assert run["error"].startswith("No source could run (budgets or provider cooldowns).")


async def test_minimum_refresh_interval_per_organization(client, internet, mode):  # noqa: F811
    mode("monitor", provider_min_refresh_minutes={"hacker_news": 120})
    admin, _ = await setup(client)
    first = await discover(admin)
    assert first["results"]["hacker_news"]["status"] == "ok"
    second = await discover(admin)
    assert second["results"]["hacker_news"]["status"] == "skipped_recent"
    assert second["results"]["google_trends"]["status"] == "ok"


# --- Instagram hashtags -------------------------------------------------------------


async def test_hashtag_window_counts_unique_tags_per_account(db, mode):
    mode("enforce", instagram_hashtag_weekly_cap=2)
    await quota.reserve_hashtag("1784", "ai")
    await quota.reserve_hashtag("1784", "AI")  # same tag: no new slot
    await quota.reserve_hashtag("1784", "seo")
    with pytest.raises(SourceError) as exc:
        await quota.reserve_hashtag("1784", "cloud")
    assert exc.value.kind == SourceErrorKind.BUDGET_EXHAUSTED and "2 of 2" in exc.value.message
    await quota.reserve_hashtag("1784", "seo")  # already counted: still allowed
    await quota.reserve_hashtag("9999", "cloud")  # another account has its own window
    assert await quota.hashtags_in_window("1784") == 2

    # Slots free up after 7 days. Aged on the database clock, which the window
    # and prune queries use (the test host's clock may differ by milliseconds).
    await db.execute(
        update(InstagramHashtagUse)
        .where(InstagramHashtagUse.hashtag == "ai")
        .values(last_used_at=func.now() - timedelta(days=8))
    )
    await db.commit()
    await quota.reserve_hashtag("1784", "cloud")
    assert await quota.prune_hashtags() == 1
    stored = {r.account for r in await db.scalars(select(InstagramHashtagUse))}
    assert "1784" not in stored  # only a fingerprint of the account id is kept


async def test_concurrent_runs_cannot_both_take_the_last_hashtag_slot(db, mode):
    mode("enforce", instagram_hashtag_weekly_cap=1)

    async def attempt(tag):
        try:
            await quota.reserve_hashtag("1784", tag)
            return "ok"
        except SourceError:
            return "refused"

    results = await asyncio.gather(attempt("a"), attempt("b"), attempt("c"))
    assert sorted(results) == ["ok", "refused", "refused"]


async def test_instagram_cache_hits_use_no_hashtag_slot(db, mode, monkeypatch):
    mode("monitor")
    monkeypatch.setattr("app.sources.instagram.HASHTAG_GAP", 0)
    net = FakeInternet()
    await run_source("instagram", settings=ALL_KEYS, keywords=["ai", "seo"], net=net)
    await run_source("instagram", settings=ALL_KEYS, keywords=["ai"], net=net)  # another org
    assert await quota.hashtags_in_window(ALL_KEYS.instagram_business_account_id) == 2
    searches = [c for c in net.calls if "ig_hashtag_search" in c]
    assert len(searches) == 2
