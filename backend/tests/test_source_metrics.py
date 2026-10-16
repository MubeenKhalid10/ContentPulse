"""Trend-source metrics on /health/metrics: sanitized, optionally token-protected."""

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.sources import quota
from tests.test_provider_cache import run_source
from tests.test_trends_api import discover, internet, setup  # noqa: F401
from tests.trend_fixtures import FakeInternet


@pytest.fixture
def metrics_client(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "provider_daily_budgets", {"gnews": 50})
    from app.main import create_app

    app = create_app()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_metrics_cover_requests_cache_usage_cooldowns_and_runs(
    client,
    internet,  # noqa: F811
    metrics_client,
):
    secret = "GN-METRICS-SECRET"
    settings = Settings(_env_file=None, gnews_api_key=secret)
    net = FakeInternet()
    await run_source("gnews", settings=settings, keywords=["private-keyword"], net=net)
    await run_source("gnews", settings=settings, keywords=["private-keyword"], net=net)  # cached
    await quota.start_cooldown("x", status=429, retry_after=900)
    admin, org = await setup(client)
    await discover(admin)

    async with metrics_client as mc:
        resp = await mc.get("/health/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert 'trend_provider_requests_total{outcome="ok",source="gnews"}' in body
    assert "trend_provider_latency_seconds_count" in body
    assert 'trend_provider_cache_events_total{event="memory_hit",source="gnews"}' in body
    assert 'trend_provider_usage_today{field="completed",source="gnews"}' in body
    assert 'trend_provider_budget_remaining{source="gnews"}' in body
    assert 'trend_provider_cooldown_seconds{source="x"}' in body
    assert 'trend_discovery_runs_total{status="succeeded",trigger="manual"}' in body
    assert 'trend_organizations_by_frequency{frequency="every_3_hours"} 1' in body
    # Nothing tenant-specific or secret.
    for private in (secret, "private-keyword", org["id"], "GPT-6"):
        assert private not in body


async def test_metrics_token(metrics_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_token", "scrape-me")
    async with metrics_client as mc:
        assert (await mc.get("/health/metrics")).status_code == 401
        bad = await mc.get("/health/metrics", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401
        ok = await mc.get("/health/metrics", headers={"Authorization": "Bearer scrape-me"})
        assert ok.status_code == 200
