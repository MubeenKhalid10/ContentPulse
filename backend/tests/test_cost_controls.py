"""AI cost controls: prices and cost_usd, cached-token accounting, Gemini as
the last fallback, right-sized output allowances, the alignment gate and
failure backoff, idempotent Kie images, and embedding reuse on re-index."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.ai import pricing
from app.ai.provider import AIError, AIErrorKind, AnthropicProvider, GeminiProvider
from app.db.session import SessionLocal
from app.models.ai import LLMRequest
from app.models.enums import JobStatus
from tests import test_llm_gateway as gateway_tests
from tests.test_llm_gateway import SCHEMA, FakeModel, call, gateway, make_org

# The gateway tests' fixtures (simulated clock, limiter settings).
clock = gateway_tests.clock
configure = gateway_tests.configure


@pytest.fixture
def prices(monkeypatch):
    """Price the fake models; pricing reads the process settings."""

    def apply(table: dict) -> None:
        from app.core.config import get_settings

        settings = get_settings().model_copy(update={"llm_prices": table})
        monkeypatch.setattr(pricing, "get_settings", lambda: settings)

    return apply


# --- Prices --------------------------------------------------------------------


def test_cost_from_the_price_table(prices):
    prices({"fakeai/m1": {"input_per_million": 1.0, "output_per_million": 4.0}})
    # 1M input (250k cached at the input rate by default) + 0.5M output.
    assert pricing.cost_usd(
        "fakeai", "m1", input_tokens=1_000_000, output_tokens=500_000, cached_input_tokens=250_000
    ) == Decimal("3.000000")
    prices(
        {
            "fakeai/*": {
                "input_per_million": 1.0,
                "output_per_million": 4.0,
                "cached_input_per_million": 0.1,
            },
            "img/x": {"per_image": 0.04},
        }
    )
    assert pricing.cost_usd(
        "fakeai", "any", input_tokens=1_000_000, cached_input_tokens=500_000
    ) == Decimal("0.550000")
    assert pricing.cost_usd("img", "x", images=2) == Decimal("0.080000")
    # Unknown model or no usage: no cost, never a guess.
    assert pricing.cost_usd("other", "m", input_tokens=10) is None
    assert pricing.cost_usd("fakeai", "m1") is None


def test_price_file_covers_the_configured_models():
    file_prices = pricing._file_prices("llm_prices.json")
    for key in ("groq/qwen/qwen3.8-27b", "groq/openai/gpt-oss-120b", "gemini/gemini-embedding-2"):
        assert key in file_prices


async def test_cost_and_cached_tokens_are_recorded(configure, clock, prices):
    settings = configure()
    prices({"fakeai/m1": {"input_per_million": 2.0, "output_per_million": 8.0}})

    class Cached(FakeModel):
        async def generate_structured(self, **kwargs):
            result = await super().generate_structured(**kwargs)
            result.cached_input_tokens = 400
            return result

    gw = gateway([Cached(tokens=(1000, 500))], settings, clock)
    org = await make_org("Costly")
    await call(gw, workflow="w", organization_id=org, cache=True)
    await call(gw, workflow="w", organization_id=org, cache=True)  # cache hit
    async with SessionLocal() as db:
        rows = list(await db.scalars(select(LLMRequest).order_by(LLMRequest.created_at)))
    assert [(r.status, r.cached_input_tokens) for r in rows] == [
        ("succeeded", 400),
        ("cached", None),
    ]
    assert rows[0].cost_usd == Decimal("0.006000")  # 1000 x $2/M + 500 x $8/M
    assert rows[1].cost_usd == 0


# --- Provider usage accounting ----------------------------------------------------


async def test_anthropic_input_tokens_include_cache_reads_and_writes():
    usage = SimpleNamespace(
        input_tokens=50,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=100,
        output_tokens=20,
    )
    response = SimpleNamespace(
        stop_reason="end_turn",
        model="claude-test",
        content=[SimpleNamespace(type="text", text="{}")],
        usage=usage,
    )

    class Messages:
        async def create(self, **_):
            return response

    client = SimpleNamespace(beta=SimpleNamespace(messages=Messages()))
    provider = AnthropicProvider(
        model="claude-test", effort="low", api_key="k", timeout=5, client=client
    )
    result = await provider.generate_structured(system="S", prompt="P", schema=SCHEMA)
    assert (result.input_tokens, result.cached_input_tokens) == (1050, 900)


async def test_gemini_reports_implicitly_cached_tokens_and_cut_off_answers():
    def reply(finish: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": finish, "content": {"parts": [{"text": "{}"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 800,
                    "cachedContentTokenCount": 600,
                    "candidatesTokenCount": 10,
                },
            },
        )

    finish = iter(["STOP", "MAX_TOKENS"])
    gemini = GeminiProvider(
        model="gemini-test",
        api_key="k",
        timeout=5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: reply(next(finish)))),
    )
    result = await gemini.generate_structured(system="S", prompt="P", schema=SCHEMA)
    assert (result.input_tokens, result.cached_input_tokens) == (800, 600)
    with pytest.raises(AIError) as exc:
        await gemini.generate_structured(system="S", prompt="P", schema=SCHEMA)
    assert exc.value.kind == AIErrorKind.OVERSIZED and exc.value.truncated


# --- Gemini as the last fallback --------------------------------------------------


def test_gemini_is_the_last_fallback_of_default_chains(monkeypatch):
    from app.ai.provider import route
    from app.core.config import Settings

    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        llm_provider="groq",
        llm_model="qwen/qwen3.8-27b",
        llm_fallback_model="openai/gpt-oss-120b",
        llm_routes={"design_brief": ["groq/openai/gpt-oss-120b"]},
    )
    assert [str(t) for t in route("trend_alignment", settings)] == [
        "groq/qwen/qwen3.8-27b",
        "groq/openai/gpt-oss-120b",
        "gemini/gemini-3.5-flash",
    ]
    # Explicit per-workflow routes are left as written.
    assert [str(t) for t in route("design_brief", settings)] == ["groq/openai/gpt-oss-120b"]
    # A chain that already has Gemini doesn't get a second one; empty = off.
    gemini = Settings(_env_file=None, llm_provider="gemini")
    assert [str(t) for t in route("w", gemini)] == [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash",
    ]
    off = settings.model_copy(update={"llm_gemini_fallback_model": None})
    assert all(t.provider == "groq" for t in route("trend_alignment", off))
    # No Gemini key: nothing is added.
    monkeypatch.delenv("GEMINI_API_KEY")
    no_key = settings.model_copy(update={"gemini_api_key": None})
    assert all(t.provider == "groq" for t in route("trend_alignment", no_key))


# --- Output allowances ------------------------------------------------------------


async def test_a_cut_off_answer_is_retried_once_with_double_the_allowance(configure, clock):
    settings = configure()

    class Truncating(FakeModel):
        def __init__(self, cuts: int) -> None:
            super().__init__()
            self.cuts = cuts
            self.allowances: list[int] = []

        async def generate_structured(self, *, max_tokens=16000, **kwargs):
            self.allowances.append(max_tokens)
            if len(self.allowances) <= self.cuts:
                raise AIError(AIErrorKind.OVERSIZED, "cut off", truncated=True)
            return await super().generate_structured(max_tokens=max_tokens, **kwargs)

    once = Truncating(cuts=1)
    await call(gateway([once], settings, clock), max_tokens=2000)
    assert once.allowances == [2000, 4000]

    always = Truncating(cuts=5)
    fallback = FakeModel("m2")
    result = await call(gateway([always, fallback], settings, clock), max_tokens=2000)
    assert always.allowances == [2000, 4000] and result.model == "m2"


# --- Alignment gate and failure backoff -------------------------------------------


def test_gate_needs_a_keyword_service_or_knowledge_signal():
    from app.models.enums import RelevanceLevel
    from app.services.alignment.result import AlignmentResult
    from app.services.alignment.service import has_signal

    def rules(fit: int) -> AlignmentResult:
        return AlignmentResult(
            engine="rules",
            classification=RelevanceLevel.NOT_RELEVANT,
            confidence=0.5,
            organization_fit=fit,
            audience_relevance=None,
            matched_services=[],
            reason="",
        )

    assert not has_signal(rules(10))  # the baseline: nothing connects
    assert has_signal(rules(25)) and has_signal(rules(85))


class FakeDB:
    def __init__(self, rows) -> None:
        self.rows = rows

    async def execute(self, _query):
        return self.rows


def job(trend_id, status, *, kind=None, mentions=None, hours_ago=1.0):
    now = datetime.now(UTC)
    return SimpleNamespace(
        entity_id=trend_id,
        status=status,
        result={"error_kind": kind, "mention_count": mentions} if kind else {},
        completed_at=now - timedelta(hours=hours_ago),
    )


async def test_failed_trends_back_off_and_final_failures_wait_for_new_coverage(monkeypatch):
    from app.core.config import get_settings
    from app.services.alignment import service

    settings = get_settings().model_copy(
        update={"alignment_failure_backoff_hours": 3.0, "alignment_max_failures": 3}
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    t = [SimpleNamespace(id=uuid.uuid4(), mention_count=5) for _ in range(6)]
    F, S = JobStatus.FAILED, JobStatus.SUCCEEDED
    rows = [  # newest first, as the query orders them
        job(t[0].id, F, kind="bad_output", mentions=5, hours_ago=100),  # final, same coverage
        job(t[1].id, F, kind="refused", mentions=3, hours_ago=1),  # final, coverage changed
        job(t[2].id, F, kind="unavailable", mentions=5, hours_ago=1),  # 1st failure: wait 3h
        job(t[3].id, F, kind="rate_limited", mentions=5, hours_ago=7),  # 2nd failure: 6h passed
        job(t[3].id, F, kind="rate_limited", mentions=5, hours_ago=20),
        job(t[4].id, F, kind="unavailable", mentions=5, hours_ago=100),  # 3 failures: stop
        job(t[4].id, F, kind="unavailable", mentions=5, hours_ago=200),
        job(t[4].id, F, kind="unavailable", mentions=5, hours_ago=300),
        job(t[5].id, F, kind="unavailable", mentions=5, hours_ago=200),  # after a success
        job(t[5].id, S, hours_ago=300),
        job(t[5].id, F, kind="unavailable", mentions=5, hours_ago=400),
        job(t[5].id, F, kind="unavailable", mentions=5, hours_ago=500),
    ]
    held = await service.failure_hold(FakeDB(rows), t)
    assert held == {t[0].id, t[2].id, t[4].id}


async def test_automatic_analysis_query_runs(monkeypatch):
    """The gate and backoff conditions compile and run against Postgres."""
    from app.ai.provider import set_ai_provider
    from app.services.alignment.service import analyze_organization

    set_ai_provider(FakeModel())
    try:
        assert await analyze_organization(await make_org("Quiet")) == 0
    finally:
        set_ai_provider(None)


# --- Kie images -------------------------------------------------------------------


def kie_server(*, poll_failures: int = 0):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    seen = {"created": 0, "polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/createTask"):
            seen["created"] += 1
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "t1"}})
        if request.url.path.endswith("/recordInfo"):
            seen["polls"] += 1
            if seen["polls"] <= poll_failures:
                return httpx.Response(503, json={"code": 503, "msg": "busy"})
            result = json.dumps({"resultUrls": ["https://files.example.com/a.png"]})
            return httpx.Response(
                200, json={"code": 200, "data": {"state": "success", "resultJson": result}}
            )
        return httpx.Response(200, content=png)

    return handler, seen


def kie(handler):
    from app.ai.images import KieImages

    images = KieImages(
        model="seedream/test",
        api_key="k",
        timeout=60,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def no_wait(_):
        return None

    images.sleep = no_wait
    return images


async def test_kie_retries_poll_without_creating_another_task(configure, clock):
    from app.ai.images import generate_image, set_image_provider

    settings = configure(llm_max_retries=2)
    handler, seen = kie_server(poll_failures=1)
    set_image_provider(kie(handler))
    told: list[str] = []

    async def remember(task_id: str) -> None:
        told.append(task_id)

    try:
        org = await make_org("Pictures")
        image = await generate_image(
            "a cat", "1:1", organization_id=org, settings=settings, on_task=remember
        )
        assert image.data.startswith(b"\x89PNG")
        assert seen == {"created": 1, "polls": 2} and told == ["t1"]

        # A later run with the saved task id only polls: no task, no cap slot.
        acquired: list = []
        from app.ai.limits import quota_limiter

        real_acquire = quota_limiter.acquire

        async def counting(*args, **kwargs):
            acquired.append(args)
            return await real_acquire(*args, **kwargs)

        quota_limiter.acquire = counting
        try:
            await generate_image(
                "a cat", "1:1", organization_id=org, settings=settings, task_id="t1"
            )
        finally:
            quota_limiter.acquire = real_acquire
        assert seen["created"] == 1 and acquired == []
    finally:
        set_image_provider(None)

    async with SessionLocal() as db:
        rows = list(await db.scalars(select(LLMRequest).where(LLMRequest.status == "succeeded")))
    assert [r.image_count for r in rows] == [1, 1]


async def test_kie_slow_task_or_failed_download_is_retryable():
    still_working = lambda r: httpx.Response(  # noqa: E731
        200, json={"code": 200, "data": {"state": "generating"}}
    )
    with pytest.raises(AIError) as exc:
        await kie(still_working).fetch("t9")
    assert exc.value.retryable and "t9" in exc.value.message

    def broken_download(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/recordInfo"):
            result = json.dumps({"resultUrls": ["https://files.example.com/a.png"]})
            return httpx.Response(
                200, json={"code": 200, "data": {"state": "success", "resultJson": result}}
            )
        return httpx.Response(500)

    with pytest.raises(AIError) as exc:
        await kie(broken_download).fetch("t9")
    assert exc.value.retryable


# --- Re-indexing ------------------------------------------------------------------


async def test_reindex_reuses_vectors_of_unchanged_chunks(db):
    from app.models.knowledge import EMBEDDING_DIMENSIONS, KnowledgeDocument
    from app.services.knowledge.indexer import index_document

    class Counting:
        name, model, batch_size = "fakeembed", "e1", 64

        def __init__(self) -> None:
            self.texts: list[str] = []

        async def embed(self, texts):
            self.texts += texts
            return [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]

    org = await make_org("Library")
    doc = KnowledgeDocument(
        organization_id=org,
        source_url="https://example.com/a",
        document_type="web_page",
        title="Services",
        content="# Consulting\n\n"
        + "We advise teams on data. " * 40
        + "\n\n# Training\n\n"
        + "Workshops for analysts. " * 40,
    )
    db.add(doc)
    await db.flush()
    provider = Counting()
    first = await index_document(db, doc, provider)
    await db.commit()
    embedded = len(provider.texts)
    assert first.embedded and embedded >= 1

    await index_document(db, doc, provider)  # unchanged: no request
    await db.commit()
    assert len(provider.texts) == embedded

    doc.content += "\n\n# Pricing\n\n" + "Fixed fees per project. " * 40
    await index_document(db, doc, provider)  # only the new text is embedded
    await db.commit()
    assert 1 <= len(provider.texts) - embedded < embedded + 1
