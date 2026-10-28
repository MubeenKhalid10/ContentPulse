import os
import tempfile

# Must be set before the app (and its engine) is imported.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://contentpulse:contentpulse@localhost:5434/contentpulse_test",
)


def _refuse_unsafe_database(url: str) -> None:
    """The suite drops the whole schema and truncates every table: it only ever
    runs against a local database whose name says it is for tests."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if "test" not in name.lower() or not (
        local or os.environ.get("ALLOW_REMOTE_TEST_DATABASE") == "1"
    ):
        raise RuntimeError(
            f"Refusing to run the tests against database {name!r} on {parts.hostname!r}: "
            "TEST_DATABASE_URL must point at a local database with 'test' in its name "
            "(ALLOW_REMOTE_TEST_DATABASE=1 allows a non-local host)."
        )


_refuse_unsafe_database(TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ["AUTH_PROVIDER"] = "local"
os.environ["TREND_SCHEDULER_ENABLED"] = "false"
# Tests run discovery repeatedly; test_discovery_window.py turns the window on.
os.environ["TREND_MANUAL_REUSE_WINDOW"] = "false"
os.environ["TASK_BACKEND"] = "inprocess"
# The relevance pre-filter drops collected items that don't match the test
# organization's profile, which would empty every fixture-driven discovery run:
# off by default here, switched on in the tests that cover it.
os.environ["TREND_RELEVANCE_PREFILTER"] = "false"
# Opt-in per test (tests/test_operations.py): limits and retry delays would
# otherwise make unrelated tests slow or order-dependent.
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["RATE_LIMIT_BACKEND"] = "memory"
os.environ["JOB_RETRY_DELAYS"] = "[]"
# LLM gateway: no published limits, no in-gateway retries, no shared Redis
# state (tests/test_llm_gateway.py opts in to each).
os.environ["LLM_LIMITS_FILE"] = "off"
os.environ["EMBEDDING_PROVIDER"] = "none"
os.environ["LLM_MAX_RETRIES"] = "0"
os.environ["LLM_LIMITER_BACKEND"] = "memory"
# Creative uploads land in a throwaway directory, never backend/storage.
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="contentpulse-test-")

from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.ai.gateway import llm_cache  # noqa: E402
from app.ai.limits import quota_limiter  # noqa: E402
from app.ai.metrics import metrics  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.sources.base import request_cache, token_cache  # noqa: E402
from app.sources.provider_cache import cache_stats  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-battery"


def _reset_schema() -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    async def reset() -> None:
        scratch = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        try:
            async with scratch.begin() as conn:
                await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        finally:
            await scratch.dispose()

    asyncio.run(reset())


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Apply migrations from scratch once per run. The schema is dropped rather
    than downgraded: some migrations are deliberately irreversible."""
    _reset_schema()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def offline_trendspy(monkeypatch) -> None:
    """trendspy uses `requests`, not httpx: keep the suite off the real Google."""
    monkeypatch.setattr(
        "app.sources.google_trends_tech.fetch_tech_trends", lambda geo, hours=24: []
    )


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    request_cache.clear()  # trend source responses are cached across runs
    token_cache.clear()
    cache_stats.reset()
    quota_limiter.reset()
    llm_cache.clear()
    metrics.reset()
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def db():
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class Actor:
    """A signed-in user with helpers that attach their bearer token."""

    def __init__(self, client: httpx.AsyncClient, token: str, user: dict) -> None:
        self.client = client
        self.token = token
        self.user = user
        self.headers = {"Authorization": f"Bearer {token}"}

    async def request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {**self.headers, **kw.pop("headers", {})}
        return await self.client.request(method, url, headers=headers, **kw)

    async def get(self, url: str, **kw) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:
        return await self.request("POST", url, **kw)

    async def patch(self, url: str, **kw) -> httpx.Response:
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw) -> httpx.Response:
        return await self.request("DELETE", url, **kw)


async def register(client: httpx.AsyncClient, email: str, name: str = "Test User") -> Actor:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert resp.status_code == 201, resp.text
    client.cookies.clear()  # tests authenticate explicitly via bearer tokens
    body = resp.json()
    return Actor(client, body["access_token"], body["user"])


async def create_org(actor: Actor, name: str = "Acme Software") -> dict:
    resp = await actor.post(
        "/api/v1/organizations",
        json={"name": name, "website_url": "https://acme.example.com", "timezone": "Europe/London"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_member(
    client: httpx.AsyncClient, admin: Actor, org_id: str, email: str, role: str
) -> Actor:
    """Invite a new user with `role` and accept the invitation as them."""
    resp = await admin.post(
        f"/api/v1/organizations/{org_id}/invitations", json={"email": email, "role": role}
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["invite_url"].rsplit("/", 1)[1]
    resp = await client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": role.title(), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    body = resp.json()
    return Actor(client, body["access_token"], body["user"])
