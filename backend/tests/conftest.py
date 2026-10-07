import os
import tempfile

# Must be set before the app (and its engine) is imported.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://contentpulse:contentpulse@localhost:5434/contentpulse_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ["AUTH_PROVIDER"] = "local"
os.environ["TREND_SCHEDULER_ENABLED"] = "false"
os.environ["TASK_BACKEND"] = "inprocess"
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
from app.sources.base import request_cache  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Apply migrations from scratch once per run (also exercises downgrade)."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    request_cache.clear()  # trend source responses are cached across runs
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
