"""LLM gateway: quotas (RPM, TPM, RPD, concurrency, budgets), queueing,
retries, Retry-After, fallback, caching, accounting, and limits shared across
worker processes through Redis."""

import asyncio
import json
import re
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.ai import limits
from app.ai.gateway import LLMGateway
from app.ai.limits import LimitsCatalog, QuotaExceeded, QuotaLimiter, quota_limiter
from app.ai.metrics import metrics
from app.ai.provider import (
    USER_MESSAGES,
    AIError,
    AIErrorKind,
    GeminiProvider,
    OpenAICompatibleProvider,
    StructuredResult,
    retry_after_from,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.ai import LLMRequest
from app.models.organization import Organization

SCHEMA = {"type": "object"}


class Clock:
    """Simulated time for the limiter, the gateway and their sleeps."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += max(0.0, seconds)
        await asyncio.sleep(0)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(limits, "monotonic", c)
    monkeypatch.setattr(quota_limiter, "sleep", c.sleep)
    return c


@pytest.fixture
def configure():
    """Apply test settings to the shared limiter; restore afterwards."""

    def apply(**overrides):
        settings = get_settings().model_copy(update={"llm_retry_base_delay": 1.0, **overrides})
        quota_limiter.configure(settings)
        return settings

    yield apply
    quota_limiter.configure(get_settings())


class FakeModel:
    """A provider adapter that records when it was called. `script` items
    (exceptions) are raised by successive calls; then it succeeds."""

    def __init__(self, model: str = "m1", *, script=(), tokens=(100, 50), delay: float = 0):
        self.name, self.model = "fakeai", model
        self.script = list(script)
        self.tokens = tokens
        self.delay = delay
        self.calls: list[float] = []
        self.in_flight = self.max_in_flight = 0

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        self.calls.append(limits.monotonic())
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.script:
                step = self.script.pop(0)
                if isinstance(step, Exception):
                    raise step
            return StructuredResult({"answer": self.model}, self.model, *self.tokens)
        finally:
            self.in_flight -= 1


class StrictProvider(FakeModel):
    """Behaves like a provider enforcing `rpm` itself: over it, a 429."""

    def __init__(self, rpm: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rpm = rpm
        self.rejected = 0

    async def generate_structured(self, **kwargs):
        now = limits.monotonic()
        if sum(1 for t in self.calls if t > now - 60) >= self.rpm:
            self.rejected += 1
            raise AIError(AIErrorKind.RATE_LIMITED, "429 from provider")
        return await super().generate_structured(**kwargs)


def gateway(models, settings, clock: Clock | None = None) -> LLMGateway:
    gw = LLMGateway(list(models), settings)
    if clock:
        gw.sleep = clock.sleep
    return gw


async def call(gw: LLMGateway, prompt: str = "P", **kwargs) -> StructuredResult:
    return await gw.generate_structured(system="S", prompt=prompt, schema=SCHEMA, **kwargs)


def max_in_any_minute(times: list[float]) -> int:
    return max((sum(1 for t in times if start <= t < start + 60) for start in times), default=0)


def limits_for(**values) -> dict:
    return {"llm_limits": {"fakeai/m1": values}}


# --- RPM / TPM / RPD are independent ------------------------------------------------


async def test_burst_stays_under_rpm_with_safety_margin(configure, clock):
    """The reported incident: 16 requests in a burst against a 15 RPM model."""
    settings = configure(**limits_for(rpm=15), llm_rate_limit_safety_factor=0.8)
    provider = StrictProvider(rpm=15)
    gw = gateway([provider], settings, clock)

    results = await asyncio.gather(*(call(gw) for _ in range(16)))

    assert len(results) == 16 and provider.rejected == 0  # never saw a 429
    assert max_in_any_minute(provider.calls) == 12  # 15 x 0.8: waited instead
    assert provider.calls[12] - provider.calls[0] >= 60


async def test_rpm_blocks_even_with_plenty_of_tpm(configure, clock):
    settings = configure(**limits_for(rpm=2, tpm=1_000_000), llm_rate_limit_safety_factor=1)
    model = FakeModel()
    gw = gateway([model], settings, clock)
    for _ in range(3):
        await call(gw)
    assert model.calls[1] == model.calls[0]  # no waiting while RPM has room
    assert model.calls[2] - model.calls[0] >= 60


async def test_tpm_blocks_on_actual_usage_and_not_otherwise(configure, clock):
    settings = configure(**limits_for(tpm=1000), llm_rate_limit_safety_factor=1)
    heavy = FakeModel(tokens=(990, 50))  # the small estimate is corrected to 1040 actual
    gw = gateway([heavy], settings, clock)
    await call(gw)
    await call(gw)
    assert heavy.calls[1] - heavy.calls[0] >= 60

    light = FakeModel(tokens=(10, 10))
    gw = gateway([light], configure(**limits_for(tpm=1_000_000)), clock)
    for _ in range(10):
        await call(gw)
    assert len(set(light.calls)) == 1  # TPM to spare: nothing waited


async def test_daily_request_limit_moves_to_the_fallback_model(configure, clock):
    settings = configure(**limits_for(rpd=3), llm_rate_limit_safety_factor=1)
    primary, fallback = FakeModel("m1"), FakeModel("m2")
    gw = gateway([primary], settings, clock)
    for _ in range(3):
        await call(gw)
    with pytest.raises(AIError) as exc:
        await call(gw)
    assert exc.value.kind == AIErrorKind.QUOTA_EXHAUSTED
    assert exc.value.user_message == USER_MESSAGES[AIErrorKind.QUOTA_EXHAUSTED]
    assert "today" in exc.value.user_message

    result = await call(gateway([primary, fallback], settings, clock))
    assert result.fallback_used and len(primary.calls) == 3 and len(fallback.calls) == 1


async def test_application_budget_stops_every_model(configure, clock):
    settings = configure(llm_daily_request_budget=2)
    primary, fallback = FakeModel("m1", script=[]), FakeModel("m2")
    gw = gateway([primary, fallback], settings, clock)
    await call(gw)
    await call(gw)
    with pytest.raises(AIError) as exc:
        await call(gw)
    assert exc.value.kind == AIErrorKind.BUDGET_EXHAUSTED
    assert fallback.calls == []  # a budget is not a reason to spend elsewhere


async def test_workflow_budget_only_limits_that_workflow(configure, clock):
    settings = configure(llm_workflow_daily_budgets={"trend_alignment": 1})
    gw = gateway([FakeModel()], settings, clock)
    await call(gw, workflow="trend_alignment")
    with pytest.raises(AIError):
        await call(gw, workflow="trend_alignment")
    await call(gw, workflow="post_generation")


# --- Concurrency and queueing -------------------------------------------------------


async def test_concurrency_is_never_exceeded(configure):
    settings = configure(**limits_for(concurrency=2))
    model = FakeModel(delay=0.05)
    gw = gateway([model], settings)
    results = await asyncio.gather(*(call(gw) for _ in range(6)))
    assert len(results) == 6 and model.max_in_flight == 2


async def test_interactive_calls_give_up_queueing_sooner(configure, clock):
    settings = configure(**limits_for(rpm=1), llm_rate_limit_safety_factor=1)
    model = FakeModel()
    gw = gateway([model], settings, clock)
    await call(gw)
    with pytest.raises(AIError) as exc:
        await call(gw, interactive=True)  # would need ~60s; allowed 20s
    assert exc.value.kind == AIErrorKind.RATE_LIMITED and len(model.calls) == 1
    assert "Gemini" not in exc.value.user_message

    await call(gw)  # background work waits its turn instead
    assert model.calls[1] - model.calls[0] >= 60


# --- Retries -----------------------------------------------------------------------


def openai_reply() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gpt-test",
            "choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )


def openai_model(responses: list[httpx.Response], seen: list) -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["model"])
        return responses.pop(0) if responses else openai_reply()

    return OpenAICompatibleProvider(
        name="openai",
        model="gpt-test",
        api_key="k",
        base_url="https://api.example.com/v1",
        timeout=5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    ("status", "body", "calls", "kind"),
    [
        (429, {"error": {"message": "slow"}}, 2, None),
        (500, {}, 2, None),
        (503, {}, 2, None),
        (401, {"error": {"message": "invalid api key"}}, 1, AIErrorKind.AUTH),
        (400, {"error": {"message": "bad param"}}, 1, AIErrorKind.BAD_REQUEST),
    ],
)
async def test_transient_errors_retry_with_backoff(configure, clock, status, body, calls, kind):
    settings = configure(llm_max_retries=2)
    seen: list = []
    gw = gateway([openai_model([httpx.Response(status, json=body)], seen)], settings, clock)
    if kind is None:
        result = await call(gw)
        assert result.data == {"ok": 1} and result.attempts == 2
        assert clock.slept[0] >= 0.5  # backoff: never an immediate retry
    else:
        with pytest.raises(AIError) as exc:
            await call(gw)
        assert exc.value.kind == kind
    assert len(seen) == calls


async def test_retries_are_bounded(configure, clock):
    settings = configure(llm_max_retries=2)
    seen: list = []
    errors = [httpx.Response(503, json={}) for _ in range(10)]
    with pytest.raises(AIError) as exc:
        await call(gateway([openai_model(errors, seen)], settings, clock))
    assert exc.value.kind == AIErrorKind.UNAVAILABLE and len(seen) == 3


async def test_retry_after_is_honored_and_shared(configure, clock):
    settings = configure(llm_max_retries=2)
    seen: list = []
    limited = httpx.Response(429, headers={"retry-after": "7"}, json={})
    gw = gateway([openai_model([limited], seen)], settings, clock)
    start = clock.t
    await call(gw)
    assert 7 <= clock.t - start <= 8.5 and len(seen) == 2
    # The pause applied to the model for every caller, not just this one.
    assert "cp:llm:cooldown:openai/gpt-test" in quota_limiter.memory.cooldowns


async def test_long_retry_after_falls_back_instead_of_waiting(configure, clock):
    settings = configure(llm_max_retries=2, llm_retry_max_delay=30)
    seen: list = []
    limited = httpx.Response(429, headers={"retry-after": "120"}, json={})
    fallback = FakeModel("m2")
    result = await call(gateway([openai_model([limited], seen), fallback], settings, clock))
    assert len(seen) == 1 and result.fallback_used and clock.t - 1000 < 30


def test_retry_after_parsing():
    assert retry_after_from({"retry-after": "12"}) == 12
    assert retry_after_from({"retry-after-ms": "1500"}) == 1.5
    google = {"error": {"details": [{"@type": "RetryInfo", "retryDelay": "17s"}]}}
    assert retry_after_from(None, google) == 17
    assert retry_after_from({}, {"error": {}}) is None


async def test_gemini_daily_quota_is_not_retried():
    body = {
        "error": {
            "message": "Quota exceeded",
            "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}]}],
        }
    }
    model = GeminiProvider(
        model="g",
        api_key="k",
        timeout=5,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(429, json=body))
        ),
    )
    with pytest.raises(AIError) as exc:
        await model.generate_structured(system="", prompt="", schema={})
    assert exc.value.kind == AIErrorKind.QUOTA_EXHAUSTED and not exc.value.retryable


# --- Fallback ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "falls_back"),
    [
        (AIError(AIErrorKind.RATE_LIMITED, "429"), True),
        (AIError(AIErrorKind.UNAVAILABLE, "503"), True),
        (AIError(AIErrorKind.MODEL_UNAVAILABLE, "retired"), True),
        (AIError(AIErrorKind.BAD_REQUEST, "invalid schema"), False),
        (AIError(AIErrorKind.AUTH, "bad key"), False),
        (AIError(AIErrorKind.BAD_OUTPUT, "not json"), False),
    ],
)
async def test_fallback_only_for_errors_another_model_can_fix(configure, clock, error, falls_back):
    settings = configure()
    primary, fallback = FakeModel("m1", script=[error]), FakeModel("m2")
    gw = gateway([primary, fallback], settings, clock)
    if falls_back:
        result = await call(gw)
        assert result.fallback_used and result.model == "m2"
    else:
        with pytest.raises(AIError) as exc:
            await call(gw)
        assert exc.value.kind == error.kind
        assert fallback.calls == []


async def test_all_models_failing_gives_a_clear_error(configure, clock):
    settings = configure()
    down = [FakeModel(m, script=[AIError(AIErrorKind.UNAVAILABLE, "down")]) for m in "ab"]
    with pytest.raises(AIError) as exc:
        await call(gateway(down, settings, clock))
    assert exc.value.kind == AIErrorKind.UNAVAILABLE
    assert "All configured AI models failed" in exc.value.message
    assert exc.value.user_message == (
        "AI processing is temporarily unavailable. No data was lost. Please try again shortly."
    )


async def test_fallback_can_be_disabled(configure, clock):
    settings = configure(llm_fallback_enabled=False)
    primary = FakeModel("m1", script=[AIError(AIErrorKind.UNAVAILABLE, "down")])
    fallback = FakeModel("m2")
    with pytest.raises(AIError):
        await call(gateway([primary, fallback], settings, clock))
    assert fallback.calls == []


def test_routes_are_configurable_per_workflow(monkeypatch):
    from app.ai.provider import route
    from app.core.config import Settings

    monkeypatch.setenv("GROQ_API_KEY", "g")
    settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        llm_api_key="k",
        llm_fallbacks=["groq/llama-test", "openai/gpt-test"],  # no OpenAI key: skipped
        llm_routes={"trend_alignment": ["groq/llama-test", "gemini/gemini-3.5-flash"]},
    )
    assert [str(t) for t in route("post_generation", settings)] == [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash",
        "groq/llama-test",
    ]
    assert [str(t) for t in route("trend_alignment", settings)] == [
        "groq/llama-test",
        "gemini/gemini-3.5-flash",
    ]


# --- Cache -------------------------------------------------------------------------


async def make_org(name: str) -> uuid.UUID:
    async with SessionLocal() as db:
        org = Organization(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()
        return org.id


async def test_cache_hits_misses_and_tenant_isolation(configure, clock):
    settings = configure()
    org_a, org_b = await make_org("Alpha"), await make_org("Beta")
    m1 = FakeModel("m1")
    gw = gateway([m1], settings, clock)

    first = await call(gw, organization_id=org_a, cache=True)
    again = await call(gw, organization_id=org_a, cache=True)
    assert again.cached and again.data == first.data and len(m1.calls) == 1

    # A new prompt version (system prompt) or a different model is a miss.
    await gw.generate_structured(
        system="S v2", prompt="P", schema=SCHEMA, organization_id=org_a, cache=True
    )
    assert len(m1.calls) == 2
    m2 = FakeModel("m2")
    await call(gateway([m2], settings, clock), organization_id=org_a, cache=True)
    assert len(m2.calls) == 1

    # Organization B never sees organization A's answer.
    other = await call(gw, organization_id=org_b, cache=True)
    assert not other.cached and len(m1.calls) == 3

    await call(gw, organization_id=org_a)  # not cacheable: always asks
    assert len(m1.calls) == 4

    async with SessionLocal() as db:
        cached = await db.scalars(select(LLMRequest).where(LLMRequest.status == "cached"))
        assert [r.organization_id for r in cached] == [org_a]


# --- Accounting --------------------------------------------------------------------


async def test_every_request_is_recorded(configure, clock):
    settings = configure(llm_max_retries=1)
    org = await make_org("Gamma")
    job_id = uuid.uuid4()
    primary = FakeModel(
        "m1",
        script=[AIError(AIErrorKind.RATE_LIMITED, "429"), AIError(AIErrorKind.UNAVAILABLE, "503")],
    )
    fallback = FakeModel("m2", tokens=(None, None))
    result = await call(
        gateway([primary, fallback], settings, clock),
        workflow="trend_alignment",
        organization_id=org,
        job_id=job_id,
    )
    assert result.fallback_used and result.attempts == 3

    async with SessionLocal() as db:
        rows = list(
            await db.scalars(
                select(LLMRequest).where(LLMRequest.job_id == job_id).order_by(LLMRequest.attempt)
            )
        )
    assert [(r.model, r.status, r.error_kind, r.retry_count) for r in rows] == [
        ("m1", "failed", "rate_limited", 0),
        ("m1", "failed", "unavailable", 1),
        ("m2", "succeeded", None, 0),
    ]
    assert len({r.call_id for r in rows}) == 1
    assert all(r.organization_id == org and r.workflow == "trend_alignment" for r in rows)
    assert rows[2].fallback_used and rows[2].usage_unavailable and rows[2].total_tokens is None

    labels = {"workflow": "trend_alignment"}
    assert metrics.value("llm_requests_total", **labels) == 3
    assert metrics.value("llm_retries_total", **labels) == 1
    assert metrics.value("llm_fallback_total", **labels) == 1
    assert metrics.value("llm_rate_limit_total", source="provider") == 1
    assert "llm_latency_seconds_bucket" in metrics.render()


async def test_token_usage_is_recorded_when_reported(configure, clock):
    settings = configure()
    await call(gateway([FakeModel(tokens=(120, 30))], settings, clock), workflow="w")
    async with SessionLocal() as db:
        row = await db.scalar(select(LLMRequest))
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (120, 30, 150)
    assert not row.usage_unavailable and row.latency_ms is not None


def test_limits_catalog_lookup_and_overrides():
    settings = get_settings().model_copy(
        update={
            "llm_limits_file": "llm_limits.json",
            "llm_limits": {"gemini/*": {"rpm": 4}, "bad/*": {"rpm": "lots"}},
        }
    )
    catalog = LimitsCatalog.from_settings(settings)
    assert catalog.model("gemini", "gemini-3.1-flash-lite").rpm == 15
    assert catalog.model("gemini", "anything").rpm == 4  # LLM_LIMITS override
    assert catalog.model("gemini", "anything").rpd == 250  # rest of the file entry kept
    assert catalog.model("mystery", "x").concurrency == 3  # unknown: safe default
    assert "bad/*" not in catalog.entries  # invalid entries are ignored, not fatal


# --- Shared across worker processes (Redis) -----------------------------------------


@pytest.fixture
async def redis_limiters():
    """Two limiters with their own connections: two worker processes."""
    import redis.asyncio as redis

    settings = get_settings()
    client = redis.from_url(settings.redis_url, socket_connect_timeout=0.5)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis is not reachable")
    model = f"shared-{uuid.uuid4().hex[:10]}"

    def make(**overrides):
        limiter = QuotaLimiter()
        limiter.configure(
            settings.model_copy(
                update={
                    "llm_limiter_backend": "redis",
                    "llm_rate_limit_safety_factor": 1,
                    **overrides,
                }
            )
        )
        return limiter

    yield model, make
    keys = [k async for k in client.scan_iter(match=f"cp:llm:*{model}*")]
    if keys:
        await client.delete(*keys)
    await client.aclose()


async def test_workers_share_rpm_through_redis(redis_limiters):
    model, make = redis_limiters
    workers = [make(llm_limits={f"fakeai/{model}": {"rpm": 10}}) for _ in range(2)]

    async def try_once(limiter):
        try:
            await limiter.acquire(
                "fakeai",
                model,
                tokens=10,
                organization_id=None,
                workflow="w",
                deadline=limits.monotonic() + 3,
            )
            return True
        except QuotaExceeded:
            return False

    outcomes = await asyncio.gather(*(try_once(w) for w in workers for _ in range(10)))
    assert outcomes.count(True) == 10  # not 2 x 10


async def test_workers_share_concurrency_cooldown_and_tpm(redis_limiters):
    model, make = redis_limiters
    a, b = (make(llm_limits={f"fakeai/{model}": {"concurrency": 2, "tpm": 1000}}) for _ in range(2))

    async def acquire(limiter, tokens=10, wait=0.3):
        return await limiter.acquire(
            "fakeai",
            model,
            tokens=tokens,
            organization_id=None,
            workflow="w",
            deadline=limits.monotonic() + wait,
        )

    held = [await acquire(a), await acquire(b)]
    with pytest.raises(QuotaExceeded) as exc:
        await acquire(a)
    assert exc.value.rule.kind == "lease"
    await held[0].release(actual_tokens=900)  # TPM now counts the actual 900
    with pytest.raises(QuotaExceeded) as exc:
        await acquire(b, tokens=200)
    assert exc.value.rule.kind == "window"
    await held[1].release(actual_tokens=10)

    await a.cooldown("fakeai", model, 5)
    with pytest.raises(QuotaExceeded) as exc:
        await acquire(b, tokens=1)
    assert exc.value.rule.kind == "cooldown"


async def test_burst_from_two_workers_never_exceeds_the_shared_limit(redis_limiters):
    """Load test: two workers each fire 10 requests at a 15 RPM model."""
    model, make = redis_limiters
    overrides = {
        "llm_limits": {f"fakeai/{model}": {"rpm": 15}},
        "llm_rate_limit_safety_factor": 0.8,
        # Generous so a slow Redis (Docker on a busy laptop) can't starve the
        # 12 allowed calls; the other 8 still fail fast (their slot is ~60s away).
        "llm_queue_timeout_background": 8.0,
    }
    provider = StrictProvider(rpm=15, model=model)
    workers = [LLMGateway([provider], make(**overrides).settings, make(**overrides)) for _ in "ab"]

    async def safe_call(gw):
        try:
            return await call(gw)
        except AIError as exc:
            return exc

    outcomes = await asyncio.gather(*(safe_call(gw) for gw in workers for _ in range(10)))
    succeeded = [o for o in outcomes if isinstance(o, StructuredResult)]
    queued_out = [o for o in outcomes if isinstance(o, AIError)]
    detail = [
        f"{type(o).__name__}:{getattr(o, 'kind', '')}:{getattr(o, 'message', '')}" for o in outcomes
    ]
    assert len(provider.calls) == len(succeeded) == 12, detail  # 15 x 0.8, both workers
    assert provider.rejected == 0
    assert all(e.kind == AIErrorKind.RATE_LIMITED for e in queued_out)


# --- Nothing bypasses the gateway ----------------------------------------------------


def test_no_model_calls_bypass_the_gateway():
    """Provider SDKs, endpoints and adapters are only touched inside app/ai."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    forbidden = re.compile(
        r"import anthropic|from anthropic|generativelanguage|/chat/completions|/embeddings"
        r"|GeminiProvider\(|AnthropicProvider\(|OpenAICompatibleProvider\(|OpenAIEmbeddings\("
        r"|build_adapter\("
    )
    offenders = [
        f"{path.relative_to(app_dir)}:{n}"
        for path in app_dir.rglob("*.py")
        if path.parent.name != "ai"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if forbidden.search(line)
    ]
    assert offenders == []
    gemini = Path(app_dir / "ai" / "provider.py").read_text(encoding="utf-8")
    # Adapters make one attempt; retries belong to the gateway.
    assert "asyncio.sleep" not in gemini and "max_retries=0" in gemini


# --- Embeddings ---------------------------------------------------------------------


class FlakyEmbeddings:
    name, model, batch_size = "fakeembed", "e1", 2

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[int] = []

    async def embed(self, texts):
        from app.ai.embeddings import EmbeddingError

        self.calls.append(len(texts))
        if self.failures:
            self.failures -= 1
            raise EmbeddingError("429", retryable=True, retry_after=2)
        return [[0.1] * 3 for _ in texts]


async def test_embeddings_are_batched_retried_cached_and_recorded(configure, clock):
    from app.ai.embeddings import GatedEmbeddings

    settings = configure(llm_max_retries=1)
    org_a, org_b = await make_org("Delta"), await make_org("Echo")
    inner = FlakyEmbeddings(failures=1)
    gated = GatedEmbeddings(inner, settings)
    gated.sleep = clock.sleep

    vectors = await gated.embed(["a", "b", "c"], organization_id=org_a)
    assert len(vectors) == 3 and inner.calls == [2, 2, 1]  # retried batch 1 after 2s
    assert 2 <= sum(clock.slept) <= 3

    await gated.embed(["query"], organization_id=org_a, workflow="knowledge_search")
    await gated.embed(["query"], organization_id=org_a, workflow="knowledge_search")
    await gated.embed(["query"], organization_id=org_b, workflow="knowledge_search")
    assert inner.calls[3:] == [1, 1]  # cached for A only

    async with SessionLocal() as db:
        statuses = [r.status for r in await db.scalars(select(LLMRequest))]
    assert statuses.count("failed") == 1 and statuses.count("succeeded") == 4


# --- Switching between providers --------------------------------------------------


async def test_hourly_limit_is_enforced(configure, clock):
    settings = configure(**limits_for(rph=3), llm_rate_limit_safety_factor=1)
    model, other = FakeModel(), FakeModel("m2")
    gw = gateway([model], settings, clock)
    for _ in range(3):
        await call(gw)
    # An hour's wait is longer than any queue timeout: don't sit on it...
    with pytest.raises(AIError) as exc:
        await call(gw)
    assert exc.value.kind == AIErrorKind.RATE_LIMITED and len(model.calls) == 3
    # ...switch to the next model in the chain instead.
    result = await call(gateway([model, other], settings, clock))
    assert result.model == "m2" and len(model.calls) == 3


async def test_output_cap_and_oversized_requests_fall_back(configure, clock):
    """Groq counts max_tokens against an 8K TPM: the cap keeps requests
    sendable, and a request too big for it moves to a roomier model."""
    settings = configure(**limits_for(max_output_tokens=4000))
    seen: list[int] = []

    class Capped(FakeModel):
        async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
            seen.append(max_tokens)
            return await super().generate_structured(
                system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
            )

    await call(gateway([Capped()], settings, clock), max_tokens=8000)
    assert seen == [4000]

    too_big = FakeModel("m1", script=[AIError(AIErrorKind.OVERSIZED, "413 too large")])
    roomy = FakeModel("m2")
    result = await call(gateway([too_big, roomy], settings, clock))
    assert result.model == "m2" and result.fallback_used


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (413, {"error": {"message": "Request too large for model on tokens per minute"}}),
        (400, {"error": {"message": "x", "code": "context_length_exceeded"}}),
    ],
)
async def test_openai_compatible_oversized_errors(status, body):
    model = OpenAICompatibleProvider(
        name="groq",
        model="m",
        api_key="k",
        base_url="https://api.example.com/v1",
        timeout=5,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))
        ),
    )
    with pytest.raises(AIError) as exc:
        await model.generate_structured(system="", prompt="", schema={})
    assert exc.value.kind == AIErrorKind.OVERSIZED and exc.value.try_fallback


def test_fallbacks_are_written_plainly_in_env(monkeypatch):
    from app.ai.provider import route
    from app.core.config import Settings

    monkeypatch.setenv("LLM_FALLBACKS", "groq/openai/gpt-oss-120b, cerebras/qwen-3.8-27b")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("CEREBRAS_API_KEY", "c")
    settings = Settings(_env_file=None, llm_provider="gemini", llm_api_key="k")
    assert [str(t) for t in route("post_generation", settings)] == [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash",
        "groq/openai/gpt-oss-120b",  # the model name keeps its own slash
        "cerebras/qwen-3.8-27b",
    ]
    # Switching the primary is one line: the provider's defaults apply.
    switched = Settings(_env_file=None, llm_provider="cerebras")
    assert [str(t) for t in route("post_generation", switched)][:2] == [
        "cerebras/gpt-oss-120b",
        "cerebras/qwen-3.8-27b",
    ]


async def test_check_command_reports_without_sending(monkeypatch, capsys):
    from app.ai import check
    from app.core.config import Settings

    monkeypatch.setenv("GROQ_API_KEY", "secret-groq-key")
    settings = Settings(
        _env_file=None,
        llm_provider="groq",
        llm_fallbacks=["anthropic/claude-opus-5-5"],
    )
    monkeypatch.setattr(check, "get_settings", lambda: settings)
    assert await check.main(probe=False) == 0
    out = capsys.readouterr().out
    assert "1. groq/openai/gpt-oss-120b" in out
    assert "anthropic/claude-opus-5-5  [SKIPPED: no ANTHROPIC_API_KEY]" in out
    assert "secret-groq-key" not in out


async def test_gemini_embeddings_request_shape_and_query_hint():
    from app.ai.embeddings import GatedEmbeddings, GeminiEmbeddings
    from app.models.knowledge import EMBEDDING_DIMENSIONS

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        n = len(body["requests"])
        return httpx.Response(
            200, json={"embeddings": [{"values": [0.1] * EMBEDDING_DIMENSIONS}] * n}
        )

    inner = GeminiEmbeddings(
        api_key="k",
        model="gemini-embedding-2",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    gated = GatedEmbeddings(inner)
    await gated.embed(["doc one", "doc two"])
    await gated.embed(["what do we do?"], workflow="knowledge_search")
    first, query = seen
    assert first["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert first["requests"][0]["outputDimensionality"] == EMBEDDING_DIMENSIONS
    assert query["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


def test_unknown_provider_names_never_stop_the_app(caplog):
    from app.core.config import Settings

    settings = Settings(_env_file=None, llm_provider="gemni", embedding_provider="cohere")
    assert settings.llm_provider is None and settings.embedding_provider is None
    assert Settings(_env_file=None, embedding_provider="Gemini").embedding_provider == "gemini"
