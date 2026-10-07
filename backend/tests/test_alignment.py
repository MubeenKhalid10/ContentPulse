import json
import uuid
from types import SimpleNamespace

import anthropic
import httpx
import httpx2
import pytest
from sqlalchemy import select

from app.ai.gateway import LLMGateway
from app.ai.provider import (
    USER_MESSAGES,
    AIError,
    AIErrorKind,
    AnthropicProvider,
    GeminiProvider,
    set_ai_provider,
)
from app.core.config import get_settings
from app.models.ai import AIGenerationJob, PromptTemplate
from app.models.enums import RelevanceLevel
from app.services.alignment.engines import align_with_rules
from app.services.alignment.result import (
    InvalidAlignment,
    Passage,
    parse_ai_output,
    response_schema,
)
from app.workers import trend_tasks
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register
from tests.trend_fixtures import FakeInternet

API = "/api/v1/trends"


def passages(n: int = 2) -> list[Passage]:
    return [
        Passage(
            ref=f"K{i}",
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="Services | Acme",
            url="https://acme.example.com/services",
            heading="Services › AI Solutions",
            content="We build AI agents that automate invoice processing.",
            match="keyword",
        )
        for i in range(1, n + 1)
    ]


def ai_output(**overrides) -> dict:
    data = {
        "classification": "highly_relevant",
        "confidence": 0.86,
        "organization_fit": 88,
        "audience_relevance": 74,
        "matched_services": ["AI Solutions"],
        "reason": "Acme builds the agents GPT-6 makes viable [K1].",
        "possible_angles": [
            {
                "title": "What GPT-6 changes for finance ops",
                "angle": "Show where agents now beat manual reconciliation.",
                "platforms": ["linkedin"],
                "evidence": ["K1"],
            }
        ],
        "unsupported_claims": ["Acme is an OpenAI partner"],
        "evidence": [{"passage": "K1", "supports": "Acme builds AI agents"}],
    }
    data.update(overrides)
    return data


# --- Output validation: grounding is enforced in code ----------------------------


def test_schema_uses_only_supported_constraints():
    def walk(node):
        if isinstance(node, dict):
            for banned in ("minimum", "maximum", "minLength", "maxLength", "multipleOf"):
                assert banned not in node
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(response_schema(["linkedin", "x"]))


def test_parse_drops_ungrounded_content():
    result = parse_ai_output(
        ai_output(
            matched_services=["AI Solutions", "Quantum Teleporters", "ai solutions"],
            reason="Strong fit [K1], see also [K9].",
            evidence=[{"passage": "K1", "supports": "x"}, {"passage": "K7", "supports": "y"}],
            possible_angles=[
                {
                    "title": "T",
                    "angle": "A",
                    "platforms": ["linkedin", "tiktok"],
                    "evidence": ["K1", "K5"],
                }
            ],
            confidence=1.7,
            organization_fit=140,
        ),
        service_names=["AI Solutions", "Custom Software"],
        passages=passages(1),
        platforms=["linkedin", "x"],
    )
    assert result.matched_services == ["AI Solutions"]  # invented service removed, dupes merged
    assert "[K9]" not in result.reason and "[K1]" in result.reason
    assert [e["ref"] for e in result.evidence] == ["K1"]
    assert result.angles[0].evidence == ["K1"] and result.angles[0].platforms == ["linkedin"]
    assert result.confidence == 1.0 and result.organization_fit == 100  # clamped
    assert any("Quantum Teleporters" in c for c in result.corrections)


def test_no_angles_for_weak_relevance():
    result = parse_ai_output(
        ai_output(classification="weakly_relevant"),
        service_names=["AI Solutions"],
        passages=passages(1),
        platforms=["linkedin"],
    )
    assert result.angles == []


def test_malformed_output_is_rejected():
    for bad in (
        {"classification": "kinda"},
        ai_output(reason="   "),
        ai_output(organization_fit="lots"),
    ):
        with pytest.raises(InvalidAlignment):
            parse_ai_output(bad, service_names=[], passages=[], platforms=["x"])


# --- Rule-based engine -------------------------------------------------------------


def rules(topic: str, *, services=(), passages_=(), keyword_score=0):
    ctx = SimpleNamespace(service_names=list(services))
    trend = SimpleNamespace(
        topic=topic, keywords=[], signals={"keyword_match": {"score": keyword_score}}
    )
    return align_with_rules(ctx, trend, [], list(passages_))


def test_rules_engine_levels():
    service_hit = rules("New AI Solutions rules", services=["AI Solutions"], passages_=passages(1))
    assert service_hit.classification == RelevanceLevel.HIGHLY_RELEVANT
    assert service_hit.matched_services == ["AI Solutions"]
    kb_hit = rules("invoice processing", passages_=passages(1))
    assert kb_hit.classification == RelevanceLevel.RELEVANT and "[K1]" in kb_hit.reason
    nothing = rules("Naomi Osaka")
    assert nothing.classification == RelevanceLevel.NOT_RELEVANT
    assert nothing.engine == "rules" and nothing.angles == [] and nothing.audience_relevance is None


# --- Claude provider: request shape and failure handling -------------------------


def message(text: str | None, stop_reason: str = "end_turn", model: str = "claude-opus-5-5"):
    content = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        content=content,
        model=model,
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
    )


class FakeClient:
    def __init__(self, *responses):
        self.calls: list[dict] = []
        self.responses = list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def provider(client: FakeClient, model: str = "claude-opus-5-5") -> AnthropicProvider:
    return AnthropicProvider(
        model=model,
        effort="medium",
        api_key="test",
        timeout=30,
        client=client,  # type: ignore[arg-type]
    )


async def test_claude_request_shape():
    client = FakeClient(message(json.dumps({"ok": True})))
    result = await provider(client).generate_structured(
        system="SYS", prompt="P", schema={"type": "object"}
    )
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in call  # always on for Opus 5.5; never disabled
    assert result.data == {"ok": True} and result.input_tokens == 1200


async def test_claude_refusal_and_bad_output():
    with pytest.raises(AIError) as exc:
        await provider(FakeClient(message(None, "refusal"))).generate_structured(
            system="", prompt="", schema={}
        )
    assert exc.value.kind == AIErrorKind.REFUSED and "cyber" in exc.value.message
    with pytest.raises(AIError) as exc:
        await provider(FakeClient(message("not json"))).generate_structured(
            system="", prompt="", schema={}
        )
    assert exc.value.kind == AIErrorKind.BAD_OUTPUT
    with pytest.raises(AIError) as exc:
        await provider(FakeClient(message('{"a":', "max_tokens"))).generate_structured(
            system="", prompt="", schema={}
        )
    assert exc.value.kind == AIErrorKind.OVERSIZED  # cut off: a roomier model may finish


def claude_chain(client: FakeClient) -> LLMGateway:
    return LLMGateway([provider(client), provider(client, "claude-opus-5")], get_settings())


async def test_claude_outage_falls_back_but_auth_does_not():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    outage = anthropic.APIConnectionError(request=request)
    client = FakeClient(outage, message('{"ok": 1}', model="claude-opus-5"))
    result = await claude_chain(client).generate_structured(system="", prompt="", schema={})
    assert [c["model"] for c in client.calls] == ["claude-opus-5-5", "claude-opus-5"]
    assert result.model == "claude-opus-5" and result.fallback_used

    denied = anthropic.AuthenticationError(
        "bad key", response=httpx2.Response(401, request=request), body=None
    )
    client = FakeClient(denied)
    with pytest.raises(AIError) as exc:
        await claude_chain(client).generate_structured(system="", prompt="", schema={})
    assert exc.value.kind == AIErrorKind.AUTH and len(client.calls) == 1


async def test_claude_rate_limit_carries_retry_after():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError(
        "slow down",
        response=httpx2.Response(429, request=request, headers={"retry-after": "7"}),
        body=None,
    )
    with pytest.raises(AIError) as exc:
        await provider(FakeClient(limited)).generate_structured(system="", prompt="", schema={})
    assert exc.value.kind == AIErrorKind.RATE_LIMITED and exc.value.retry_after == 7


# --- End to end through the API --------------------------------------------------


class FakeAI:
    """Deterministic stand-in for Claude: judges GPT-6 relevant, others not."""

    name = "anthropic"
    model = "claude-opus-5-5"

    def __init__(self, fail: AIError | None = None) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        from app.ai.provider import StructuredResult

        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if self.fail:
            raise self.fail
        topic = prompt.split("Topic: ", 1)[1].split("\n", 1)[0]
        has_k1 = 'id="K1"' in prompt
        if "gpt-6" in topic.lower():
            data = ai_output(
                matched_services=["AI Solutions", "Made-up Service"],
                evidence=[{"passage": "K1", "supports": "AI agents"}] if has_k1 else [],
                reason="Acme builds AI agents [K1]." if has_k1 else "Acme builds AI agents.",
            )
            if not has_k1:
                data["possible_angles"][0]["evidence"] = []
        else:
            data = ai_output(
                classification="not_relevant",
                organization_fit=4,
                audience_relevance=10,
                matched_services=[],
                reason="No connection to Acme's work.",
                possible_angles=[],
                evidence=[],
            )
        return StructuredResult(data=data, model=self.model, input_tokens=900, output_tokens=200)


@pytest.fixture
def internet(monkeypatch):
    net = FakeInternet()
    net.fail("www.reddit.com", 429)

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(
        trend_tasks,
        "http_client_factory",
        lambda s: httpx.AsyncClient(transport=httpx.MockTransport(net.handler)),
    )
    monkeypatch.setattr(trend_tasks, "resolver", resolver)
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    return net


@pytest.fixture
def fake_ai():
    ai = FakeAI()
    set_ai_provider(ai)
    yield ai
    set_ai_provider(None)


async def setup_org(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    base = f"/api/v1/organizations/{org['id']}"
    await admin.patch(
        f"{base}/settings", json={"target_markets": ["USA"], "enabled_platforms": ["linkedin", "x"]}
    )
    await admin.post(
        f"{base}/services", json={"name": "AI Solutions", "description": "AI agents for operations"}
    )
    await admin.post(
        f"{base}/knowledge/documents",
        json={
            "title": "AI agents",
            "content": "## GPT-6 agents\n\nAcme deploys GPT-6 based AI agents for finance teams.",
        },
    )
    return admin, org


async def discover(actor) -> None:
    resp = await actor.post(f"{API}/discover", json={})
    assert resp.status_code == 202, resp.text
    await runner.wait_idle()  # discovery, then the alignment job it triggers


async def gpt6_trend(actor) -> dict:
    trends = (await actor.get(API, params={"status": "all"})).json()["items"]
    return next(t for t in trends if "gpt-6" in t["topic"].lower())


async def test_discovery_triggers_ai_alignment(client, internet, fake_ai, db):
    admin, org = await setup_org(client)
    await discover(admin)

    trend = await gpt6_trend(admin)
    assert trend["relevance_level"] == "highly_relevant" and trend["status"] == "analyzed"
    assert trend["signals"]["organization_fit"]["score"] == 88
    assert trend["signals"]["audience_relevance"]["score"] == 74

    detail = (await admin.get(f"{API}/{trend['id']}")).json()
    alignment = detail["alignment"]
    assert alignment["engine"] == "ai" and alignment["model"] == "claude-opus-5-5"
    assert alignment["prompt"] == {"name": "organization_alignment", "version": 1}
    assert alignment["matched_services"] == ["AI Solutions"]  # "Made-up Service" dropped
    assert alignment["passages"][0]["title"] == "AI agents"  # RAG evidence from the KB
    assert alignment["possible_angles"][0]["platforms"] == ["linkedin"]
    assert detail["analysis"]["status"] == "succeeded" and detail["analysis"]["engine"] == "ai"

    # The org profile goes in the (cached) system prompt; KB passages with the trend.
    call = next(c for c in fake_ai.calls if "GPT-6" in c["prompt"] or "gpt-6" in c["prompt"])
    assert "AI Solutions" in call["system"] and "Acme Software" in call["system"]
    assert 'id="K1"' in call["prompt"]

    job = await db.scalar(
        select(AIGenerationJob).where(AIGenerationJob.entity_id == uuid.UUID(trend["id"]))
    )
    template = await db.get(PromptTemplate, job.prompt_template_id)
    assert (template.name, template.version) == ("organization_alignment", 1)
    assert job.input_tokens == 900 and job.status == "succeeded"

    irrelevant = (await admin.get(API, params={"relevance": "not_relevant"})).json()["items"]
    assert irrelevant and all(t["relevance_level"] == "not_relevant" for t in irrelevant)
    relevant = (await admin.get(API, params={"relevance": "relevant"})).json()["items"]
    assert [t["id"] for t in relevant] == [trend["id"]]

    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["relevant_trends"] == 1
    assert all(t["id"] not in {i["id"] for i in irrelevant} for t in summary["top_trends"])


async def test_rules_engine_without_llm(client, internet):
    admin, _ = await setup_org(client)
    status = (await admin.get("/api/v1/ai/status")).json()
    assert status == {
        "configured": False,
        "engine": "rules",
        "provider": None,
        "model": None,
        "chain": [],
    }
    await discover(admin)

    trend = await gpt6_trend(admin)
    assert trend["relevance_level"] in ("highly_relevant", "relevant")
    detail = (await admin.get(f"{API}/{trend['id']}")).json()
    assert detail["alignment"]["engine"] == "rules"
    assert detail["alignment"]["possible_angles"] == []
    assert "audience_relevance" not in detail["signals"]
    assert detail["signals"]["organization_fit"]["detail"].startswith("Rule-based estimate")


async def test_ai_failure_leaves_trend_untouched_and_retry_works(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    fake_ai.fail = AIError(AIErrorKind.UNAVAILABLE, "AI provider error (529).")
    await discover(admin)

    trend = await gpt6_trend(admin)
    assert trend["relevance_level"] is None and trend["analyzed_at"] is None
    detail = (await admin.get(f"{API}/{trend['id']}")).json()
    assert detail["analysis"]["status"] == "failed"
    assert detail["analysis"]["error"] == USER_MESSAGES[AIErrorKind.UNAVAILABLE]

    fake_ai.fail = None  # provider recovered: the retry button works
    resp = await admin.post(f"{API}/{trend['id']}/analyze")
    assert resp.status_code == 202
    await runner.wait_idle()
    detail = (await admin.get(f"{API}/{trend['id']}")).json()
    assert (
        detail["relevance_level"] == "highly_relevant"
        and detail["analysis"]["status"] == "succeeded"
    )


async def test_human_override_survives_reanalysis(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    trend = await gpt6_trend(admin)

    resp = await admin.patch(
        f"{API}/{trend['id']}/relevance", json={"relevance_level": "weakly_relevant"}
    )
    assert (
        resp.json()["relevance_level"] == "weakly_relevant" and resp.json()["relevance_overridden"]
    )

    await admin.post(f"{API}/{trend['id']}/analyze")
    await runner.wait_idle()
    detail = (await admin.get(f"{API}/{trend['id']}")).json()
    assert detail["relevance_level"] == "weakly_relevant"  # human decision wins
    assert detail["alignment"]["classification"] == "highly_relevant"  # analysis still recorded

    resp = await admin.patch(f"{API}/{trend['id']}/relevance", json={"relevance_level": None})
    assert (
        resp.json()["relevance_level"] == "highly_relevant"
        and not resp.json()["relevance_overridden"]
    )

    actions = [
        e["action"]
        for e in (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    ]
    assert {"TREND_RELEVANCE_OVERRIDDEN", "TREND_ANALYSIS_REQUESTED"} <= set(actions)


async def test_rules_estimates_upgrade_when_ai_arrives(client, internet):
    admin, _ = await setup_org(client)
    await discover(admin)
    assert (await gpt6_trend(admin))["analyzed_at"] is not None

    ai = FakeAI()
    set_ai_provider(ai)
    try:
        await discover(admin)
    finally:
        set_ai_provider(None)
    detail = (await admin.get(f"{API}/{(await gpt6_trend(admin))['id']}")).json()
    assert detail["alignment"]["engine"] == "ai"


async def test_alignment_permissions(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    trend = await gpt6_trend(admin)
    viewer = await add_member(client, admin, org["id"], "v@acme.example.com", "viewer")
    manager = await add_member(client, admin, org["id"], "cm@acme.example.com", "creator")
    assert (await viewer.post(f"{API}/{trend['id']}/analyze")).status_code == 403
    assert (
        await viewer.patch(f"{API}/{trend['id']}/relevance", json={"relevance_level": None})
    ).status_code == 403
    assert (await manager.post(f"{API}/{trend['id']}/analyze")).status_code == 202
    await runner.wait_idle()


# --- Gemini provider ----------------------------------------------------------------


def gemini_reply(
    payload: dict | None = None, *, finish: str = "STOP", parts: list | None = None
) -> httpx.Response:
    parts = parts if parts is not None else [{"text": json.dumps(payload or {"ok": True})}]
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 150},
            "modelVersion": "gemini-3.8-flash",
        },
    )


def gemini(handler, model: str = "gemini-3.8-flash") -> GeminiProvider:
    return GeminiProvider(
        model=model,
        api_key="test-key",
        timeout=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def gemini_chain(handler, **settings) -> LLMGateway:
    """Primary + same-provider fallback, as get_ai_provider builds them."""
    return LLMGateway(
        [gemini(handler), gemini(handler, "gemini-3.5-flash-lite")],
        get_settings().model_copy(update={"llm_retry_base_delay": 0, **settings}),
    )


async def test_gemini_request_shape_and_parsing():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        # A thinking part must not be mixed into the JSON answer.
        return gemini_reply(
            parts=[{"text": "pondering", "thought": True}, {"text": '{"answer": 42}'}]
        )

    result = await gemini(handler).generate_structured(
        system="SYS", prompt="P", schema={"type": "object"}
    )
    request = seen[0]
    assert request.url.path == "/v1beta/models/gemini-3.8-flash:generateContent"
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "SYS"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "P"}]}]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"] == {"type": "object"}
    assert result.data == {"answer": 42}
    assert (result.input_tokens, result.output_tokens, result.model) == (
        800,
        150,
        "gemini-3.8-flash",
    )


async def test_gemini_declines_and_bad_output():
    cases = [
        (lambda r: gemini_reply(finish="SAFETY", parts=[]), AIErrorKind.REFUSED),
        (
            lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
            AIErrorKind.REFUSED,
        ),
        (lambda r: gemini_reply(finish="MAX_TOKENS"), AIErrorKind.OVERSIZED),
        (lambda r: gemini_reply(parts=[{"text": "not json"}]), AIErrorKind.BAD_OUTPUT),
    ]
    for handler, kind in cases:
        with pytest.raises(AIError) as exc:
            await gemini(handler).generate_structured(system="", prompt="", schema={})
        assert exc.value.kind == kind


async def test_gemini_rate_limit_retries_then_falls_back():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.split("/")[-1])
        if "gemini-3.8-flash" in request.url.path:
            return httpx.Response(429, json={"error": {"message": "Quota exceeded"}})
        return gemini_reply({"ok": "fallback"})

    result = await gemini_chain(handler, llm_max_retries=2).generate_structured(
        system="", prompt="", schema={}
    )
    assert calls == ["gemini-3.8-flash:generateContent"] * 3 + [
        "gemini-3.5-flash-lite:generateContent"
    ]
    assert result.data == {"ok": "fallback"}


async def test_gemini_bad_key_is_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400, json={"error": {"message": "API key not valid. Please pass a valid API key."}}
        )

    with pytest.raises(AIError) as exc:
        await gemini_chain(handler, llm_max_retries=2).generate_structured(
            system="", prompt="", schema={}
        )
    assert exc.value.kind == AIErrorKind.AUTH and calls == 1


async def test_gemini_retired_model_falls_back_without_retrying():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.split("/")[-1])
        if "gemini-3.8-flash" in request.url.path:
            message = "This model models/gemini-3.8-flash is no longer available to new users."
            return httpx.Response(400, json={"error": {"message": message}})
        return gemini_reply({"ok": "fallback"})

    result = await gemini_chain(handler, llm_max_retries=2).generate_structured(
        system="", prompt="", schema={}
    )
    assert calls == ["gemini-3.8-flash:generateContent", "gemini-3.5-flash-lite:generateContent"]
    assert result.data == {"ok": "fallback"}


def test_provider_selection_from_settings(monkeypatch):
    from app.ai.provider import get_ai_provider
    from app.core.config import Settings

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert get_ai_provider(Settings(_env_file=None, llm_provider="gemini")) is None  # no key: rules
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert get_ai_provider(Settings(_env_file=None, llm_provider="none", llm_api_key="k")) is None
    provider = get_ai_provider(Settings(_env_file=None, llm_provider="gemini"))
    assert (provider.name, provider.model) == ("gemini", "gemini-3.8-flash")
    assert provider.chain == ["gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash"]
    # A custom model (possibly retired) falls back to the current default.
    custom = get_ai_provider(
        Settings(_env_file=None, llm_provider="gemini", llm_model="gemini-2.5-flash")
    )
    assert custom.chain == ["gemini/gemini-2.5-flash", "gemini/gemini-3.8-flash"]
