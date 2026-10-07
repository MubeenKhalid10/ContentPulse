"""Sprint 9: job dispatch (in-process or Celery), retries for transient AI
failures, rate limiting, and production settings."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.provider import USER_MESSAGES, AIError, AIErrorKind, set_ai_provider
from app.core.config import Settings, get_settings
from app.core.ratelimit import AI_PER_USER, LOGIN_PER_ACCOUNT, limiter
from app.main import app
from app.models.ai import AIGenerationJob, LLMRequest
from app.workers import tasks
from app.workers.runner import runner
from tests.conftest import PASSWORD, create_org, register
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_content import ContentAI, approved_strategy

# --- Job dispatch ---------------------------------------------------------------


async def test_enqueue_runs_in_process_by_default(monkeypatch):
    seen: list[uuid.UUID] = []

    async def job(entity_id: uuid.UUID) -> None:
        seen.append(entity_id)

    monkeypatch.setattr(tasks, "resolve", lambda name: job)
    entity = uuid.uuid4()
    tasks.enqueue("content.generate", entity)
    tasks.enqueue("content.generate", entity, countdown=0.01)  # delayed
    await runner.wait_idle()
    assert seen == [entity, entity]
    with pytest.raises(KeyError):
        tasks.enqueue("no.such.job", entity)


async def test_celery_backend_sends_tasks_and_falls_back(monkeypatch):
    from app.workers.celery_app import celery_app

    monkeypatch.setattr(get_settings(), "task_backend", "celery")
    sent: list[tuple] = []
    monkeypatch.setattr(
        celery_app, "send_task", lambda name, args, countdown: sent.append((name, args, countdown))
    )
    entity = uuid.uuid4()
    tasks.enqueue("trends.discover", entity, countdown=30)
    assert sent == [("contentpulse.trends.discover", [str(entity)], 30)]

    # Broker down: the job still runs, in-process.
    def broken(*args, **kwargs):
        raise ConnectionError("redis down")

    ran: list[uuid.UUID] = []

    async def job(entity_id):
        ran.append(entity_id)

    monkeypatch.setattr(celery_app, "send_task", broken)
    monkeypatch.setattr(tasks, "resolve", lambda name: job)
    tasks.enqueue("trends.discover", entity)
    await runner.wait_idle()
    assert ran == [entity]


def test_celery_registers_every_job_and_the_schedule():
    from app.workers.celery_app import celery_app

    for name in tasks.JOBS:
        assert f"contentpulse.{name}" in celery_app.tasks
        tasks.resolve(name)  # every job path imports
    beat = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert beat == {
        "contentpulse.schedule_discovery",
        "contentpulse.recover_stale_jobs",
        "contentpulse.prune_request_history",
    }
    assert "contentpulse.prune_request_history" in celery_app.tasks
    assert celery_app.conf.task_acks_late is True


# --- Retries (spec §56) --------------------------------------------------------------


class FlakyAI(ContentAI):
    """Fails the first `failures` post generations with a transient error."""

    def __init__(self, failures: int, kind: AIErrorKind = AIErrorKind.RATE_LIMITED) -> None:
        super().__init__()
        self.failures = failures
        self.kind = kind

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        if "<strategy>" in prompt and self.failures > 0:
            self.failures -= 1
            raise AIError(self.kind, "Gemini quota or rate limit reached.")
        return await super().generate_structured(
            system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
        )


@pytest.fixture
def retries(monkeypatch):
    monkeypatch.setattr(get_settings(), "job_retry_delays", [0, 0])


async def generate(client, ai) -> tuple[dict, AIGenerationJob, object]:
    set_ai_provider(ai)
    try:
        admin, org = await setup_org(client)
        strategy = await approved_strategy(admin, org)
        resp = await admin.post("/api/v1/content/generate", json={"strategy_id": strategy["id"]})
        await runner.wait_idle()
        return (await admin.get(f"/api/v1/content/{resp.json()['id']}")).json(), admin, org
    finally:
        set_ai_provider(None)


async def test_transient_ai_failure_is_retried(client, internet, retries, db):
    post, _, _ = await generate(client, FlakyAI(failures=1))
    assert post["generation"]["status"] == "succeeded" and post["current_version"] == 1
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    assert job.attempts == 2 and job.result["retries"] == 1


async def test_retries_are_limited(client, internet, retries, db):
    post, _, _ = await generate(client, FlakyAI(failures=10))
    assert post["generation"]["status"] == "failed" and post["current_version"] == 0
    # People see a neutral message; the provider's detail stays in the logs.
    assert post["generation"]["error"] == USER_MESSAGES[AIErrorKind.RATE_LIMITED]
    assert "Gemini" not in post["generation"]["error"]
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    assert job.attempts == 3  # first try + 2 retries


async def test_permanent_failures_are_not_retried(client, internet, retries, db):
    post, _, _ = await generate(client, FlakyAI(failures=1, kind=AIErrorKind.AUTH))
    assert post["generation"]["status"] == "failed"
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    assert job.attempts == 1


# --- Rate limits (spec §61) -----------------------------------------------------------


@pytest.fixture
def limits():
    def configure(**overrides):
        options = {"rate_limit_enabled": True, "rate_limit_backend": "memory", **overrides}
        limiter.configure(Settings(_env_file=None, **options))
        limiter.reset()

    configure()
    yield configure
    limiter.configure(get_settings())
    limiter.reset()


async def test_login_is_limited_per_account(client, limits):
    await register(client, "ada@example.com")
    for _ in range(LOGIN_PER_ACCOUNT.limit):
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}
        )
        assert resp.status_code == 401
    blocked = await client.post(
        "/api/v1/auth/login", json={"email": "ADA@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 429
    body = blocked.json()["error"]
    assert body["code"] == "RATE_LIMITED" and body["details"]["retry_after"] > 0
    assert int(blocked.headers["retry-after"]) > 0
    # Other accounts aren't affected.
    await register(client, "bo@example.com")
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "bo@example.com", "password": PASSWORD}
    )
    assert ok.status_code == 200


async def test_registration_is_limited_per_ip(client, limits):
    for i in range(20):
        await register(client, f"user{i}@example.com")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "one-too-many@example.com", "password": PASSWORD, "full_name": "X"},
    )
    assert resp.status_code == 429


async def test_ai_endpoints_are_limited_per_user(client, limits):
    alice = await register(client, "alice@example.com")
    bob = await register(client, "bob@example.com")
    body = {"strategy_id": str(uuid.uuid4())}
    for _ in range(AI_PER_USER.limit):
        assert (await alice.post("/api/v1/content/generate", json=body)).status_code != 429
    assert (await alice.post("/api/v1/content/generate", json=body)).status_code == 429
    assert (await bob.post("/api/v1/content/generate", json=body)).status_code != 429


async def test_api_cap_per_ip_and_forwarded_for(client, limits):
    # Default: forwarding headers aren't trusted, so a client can't pick its bucket.
    limits(api_rate_limit_per_minute=2)
    assert (await client.get("/api/v1/auth/config")).status_code == 200
    assert (
        await client.get("/api/v1/auth/config", headers={"X-Forwarded-For": "9.9.9.9"})
    ).status_code == 200
    assert (
        await client.get("/api/v1/auth/config", headers={"X-Forwarded-For": "8.8.8.8"})
    ).status_code == 429

    limits(api_rate_limit_per_minute=3, trusted_proxy_count=1)  # behind a load balancer
    for _ in range(3):
        assert (await client.get("/api/v1/auth/config")).status_code == 200
    blocked = await client.get("/api/v1/auth/config")
    assert blocked.status_code == 429 and blocked.headers["retry-after"]
    assert (await client.get("/health/live")).status_code == 200  # not under /api

    # Behind our proxy, the address it appends is the client; a spoofed
    # left-most value doesn't create a fresh bucket.
    other = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(3):
        assert (await client.get("/api/v1/auth/config", headers=other)).status_code == 200
    spoofed = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"}
    assert (await client.get("/api/v1/auth/config", headers=spoofed)).status_code == 429


async def test_redis_outage_falls_back_to_memory(client, limits):
    limits(
        rate_limit_backend="auto", redis_url="redis://127.0.0.1:1/0", api_rate_limit_per_minute=2
    )
    assert (await client.get("/api/v1/auth/config")).status_code == 200
    assert (await client.get("/api/v1/auth/config")).status_code == 200
    assert (await client.get("/api/v1/auth/config")).status_code == 429


async def test_redis_counters_are_shared(limits):
    import redis.asyncio as redis

    url = get_settings().redis_url
    probe = redis.from_url(url, socket_connect_timeout=0.5)
    try:
        await probe.ping()
    except Exception:
        pytest.skip("Redis isn't running (docker compose up -d)")
    finally:
        await probe.aclose()
    from app.core.ratelimit import RateLimiter, Rule

    rule = Rule(f"test-{uuid.uuid4().hex}", 2, 30)
    a, b = RateLimiter(), RateLimiter()
    for instance in (a, b):
        instance.configure(
            Settings(
                _env_file=None, rate_limit_enabled=True, rate_limit_backend="redis", redis_url=url
            )
        )
    await a.check(rule, "k")
    await b.check(rule, "k")  # a second API instance sees the same window
    with pytest.raises(Exception) as exc:
        await a.check(rule, "k")
    assert getattr(exc.value, "code", None) == "RATE_LIMITED"


# --- Production settings -------------------------------------------------------------------


async def test_cookie_secure_override(client):
    await register(client, "sec@example.com")
    settings = Settings(_env_file=None, app_env="test", cookie_secure=True)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        resp = await client.post(
            "/api/v1/auth/login", json={"email": "sec@example.com", "password": PASSWORD}
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert "secure" in resp.headers["set-cookie"].lower()
    plain = await client.post(
        "/api/v1/auth/login", json={"email": "sec@example.com", "password": PASSWORD}
    )
    assert "secure" not in plain.headers["set-cookie"].lower()  # dev default


# --- LLM gateway accounting through a real workflow --------------------------------


async def test_generation_requests_are_recorded_and_reported(client, internet, db):
    post, admin, org = await generate(client, ContentAI())
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    rows = list(await db.scalars(select(LLMRequest).where(LLMRequest.job_id == job.id)))
    assert [(r.workflow, r.status, r.organization_id) for r in rows] == [
        ("post_generation", "succeeded", job.organization_id)
    ]

    usage = (await admin.get(f"/api/v1/ai/usage?job_id={job.id}")).json()
    assert usage["requests_total"] == 1
    assert usage["requests"][0]["workflow"] == "post_generation"
    # Strategy drafting earlier in setup also went through the gateway.
    overall = (await admin.get("/api/v1/ai/usage")).json()
    assert {g["workflow"] for g in overall["groups"]} >= {"post_generation"}

    other = await register(client, "outsider@else.example.com")
    await create_org(other, "Elsewhere")
    theirs = (await other.get(f"/api/v1/ai/usage?job_id={job.id}")).json()
    assert theirs["requests_total"] == 0  # another organization sees none of it
