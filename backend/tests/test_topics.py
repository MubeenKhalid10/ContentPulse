"""Sprint 5: topic candidates, shortlisting, platform recommendation and
content strategies (spec §19-22, §39)."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.ai.provider import AIError, AIErrorKind, StructuredResult, set_ai_provider
from app.models.ai import AIGenerationJob, PromptTemplate
from app.models.enums import Platform
from app.models.topic import TopicCandidate
from app.services.topics import sync
from app.services.topics.platform_defaults import DEFAULT_RULES
from app.services.topics.platforms import RecommendationInput, recommend
from tests.conftest import add_member, create_org, register
from tests.test_alignment import API as TRENDS
from tests.test_alignment import (  # noqa: F401  (shared fixtures)
    FakeAI,
    discover,
    fake_ai,
    gpt6_trend,
    internet,
    setup_org,
)

API = "/api/v1/topics"


class StrategyAI(FakeAI):
    """FakeAI that also drafts strategies, echoing the playbook it was given."""

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        if "Plan this topic" not in prompt:
            return await super().generate_structured(
                system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
            )
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if self.fail:
            raise self.fail
        props = schema["properties"]
        data = {
            "post_type": props["post_type"]["enum"][-2],
            "objective": props["objective"]["enum"][0],
            "content_angle": "Where agents now beat manual reconciliation.",
            "target_audience": "Finance leaders at mid-size companies",
            "hook_direction": "Open with the hours finance teams lose to reconciliation.",
            "cta_direction": "Invite readers to book an AI Solutions workshop.",
            "tone": "Confident, practical",
            "recommended_format": "6-slide carousel" + "x" * 80,  # clipped to 60
            "rationale": "Decision makers on LinkedIn care about operational wins.",
        }
        return StructuredResult(data=data, model=self.model, input_tokens=500, output_tokens=120)


@pytest.fixture
def strategy_ai():
    ai = StrategyAI()
    set_ai_provider(ai)
    yield ai
    set_ai_provider(None)


async def gpt6_topic(actor, status: str = "all") -> dict:
    items = (await actor.get(API, params={"status": status})).json()["items"]
    return next(t for t in items if "gpt-6" in t["title"].lower())


async def shortlisted_topic(admin) -> dict:
    topic = await gpt6_topic(admin)
    resp = await admin.post(f"{API}/{topic['id']}/shortlist")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Topic candidates ---------------------------------------------------------


async def test_relevant_trends_become_topic_candidates(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)

    page = (await admin.get(API)).json()
    assert [t["title"].lower() for t in page["items"]] == [
        (await gpt6_trend(admin))["topic"].lower()
    ]  # not-relevant trends don't become topics
    assert page["counts"]["new"] == 1 and page["total"] == 1

    topic = page["items"][0]
    assert topic["status"] == "new" and topic["relevance_level"] == "highly_relevant"
    assert topic["matched_services"] == ["AI Solutions"]
    assert topic["recommended_platforms"][0] == "linkedin"  # the AI angle targets LinkedIn
    assert topic["opportunity_score"] is not None and topic["strategy_count"] == 0

    detail = (await admin.get(f"{API}/{topic['id']}")).json()
    assert detail["relevance_reason"].startswith("Acme builds AI agents")
    assert detail["suggested_angles"][0]["title"] == "What GPT-6 changes for finance ops"
    assert detail["unsupported_claims"] == ["Acme is an OpenAI partner"]
    # Only the organization's enabled platforms are scored, each with reasons.
    fit = {f["platform"]: f for f in detail["platform_fit"]}
    assert set(fit) == {"linkedin", "x"}
    assert any("Suggested angle for LinkedIn" in r for r in fit["linkedin"]["reasons"])
    assert fit["linkedin"]["formats"] == DEFAULT_RULES[Platform.LINKEDIN]["post_types"][:3]
    # The topic page shows the trend's context: sources, keywords, coverage.
    assert detail["trend"]["id"] == topic["trend_id"] and detail["trend"]["mentions"]
    assert (await admin.get(f"{TRENDS}/{topic['trend_id']}")).json()["topic_id"] == topic["id"]
    assert detail["strategies"] == []

    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["topics_to_review"] == 1 and summary["shortlisted_topics"] == 0


async def test_rule_based_analysis_also_creates_topics(client, internet):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)
    detail = (await admin.get(f"{API}/{topic['id']}")).json()
    assert detail["suggested_angles"] == []
    assert detail["recommended_platforms"]  # always at least one platform


async def test_reanalysis_refreshes_analysis_but_keeps_human_edits(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)
    resp = await admin.patch(
        f"{API}/{topic['id']}", json={"title": "GPT-6 for finance teams", "summary": "Mine"}
    )
    assert resp.status_code == 200 and resp.json()["title"] == "GPT-6 for finance teams"

    resp = await admin.post(f"{TRENDS}/{topic['trend_id']}/analyze")
    assert resp.status_code == 202
    from app.workers.runner import runner

    await runner.wait_idle()
    detail = (await admin.get(f"{API}/{topic['id']}")).json()
    assert detail["title"] == "GPT-6 for finance teams" and detail["summary"] == "Mine"
    assert detail["matched_services"] == ["AI Solutions"]


async def test_review_decisions_stay_in_sync_with_trends(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)
    trend_url = f"{TRENDS}/{topic['trend_id']}"

    reviewed = (await admin.post(f"{API}/{topic['id']}/review")).json()
    assert reviewed["status"] == "reviewed" and reviewed["reviewed_at"]

    shortlisted = (await admin.post(f"{API}/{topic['id']}/shortlist")).json()
    assert shortlisted["status"] == "shortlisted"
    assert (await admin.get(trend_url)).json()["status"] == "shortlisted"

    rejected = (await admin.post(f"{API}/{topic['id']}/reject")).json()
    assert rejected["status"] == "rejected"
    assert (await admin.get(trend_url)).json()["status"] == "rejected"

    restored = (await admin.post(f"{API}/{topic['id']}/restore")).json()
    assert restored["status"] == "reviewed"
    assert (await admin.get(trend_url)).json()["status"] == "analyzed"

    # The other direction: decisions on the Trends page reach the topic.
    await admin.post(f"{trend_url}/reject")
    assert (await admin.get(f"{API}/{topic['id']}")).json()["status"] == "rejected"
    await admin.post(f"{trend_url}/restore")
    assert (await admin.get(f"{API}/{topic['id']}")).json()["status"] == "reviewed"
    await admin.post(f"{trend_url}/shortlist")
    assert (await admin.get(f"{API}/{topic['id']}")).json()["status"] == "shortlisted"

    archived = (await admin.post(f"{API}/{topic['id']}/archive")).json()
    assert archived["status"] == "archived"
    resp = await admin.post(f"{API}/{topic['id']}/shortlist")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert resp.json()["error"]["details"]["allowed"] == []
    assert (await admin.patch(f"{API}/{topic['id']}", json={"title": "x"})).status_code == 409

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    actions = {entry["action"] for entry in logs}
    assert {"TOPIC_SHORTLISTED", "TOPIC_REJECTED", "TOPIC_RESTORED", "TOPIC_ARCHIVED"} <= actions


async def test_shortlisting_any_trend_creates_a_topic(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    other = (await admin.get(TRENDS, params={"relevance": "not_relevant"})).json()["items"][0]
    assert (await admin.post(f"{TRENDS}/{other['id']}/shortlist")).status_code == 200

    shortlisted = (await admin.get(API, params={"status": "shortlisted"})).json()
    assert [t["trend_id"] for t in shortlisted["items"]] == [other["id"]]
    assert shortlisted["items"][0]["relevance_level"] == "not_relevant"


async def test_filters_and_sorting(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    for params, expected in [
        ({"relevance": "relevant"}, 1),
        ({"relevance": "not_relevant"}, 0),
        ({"platform": "linkedin"}, 1),
        ({"platform": "instagram"}, 0),
        ({"q": "gpt"}, 1),
        ({"q": "nothing-like-this"}, 0),
        ({"status": "shortlisted"}, 0),
        ({"sort": "relevance"}, 1),
        ({"sort": "recent"}, 1),
    ]:
        resp = await admin.get(API, params=params)
        assert resp.status_code == 200, (params, resp.text)
        assert resp.json()["total"] == expected, params
    assert (await admin.get(API, params={"status": "bogus"})).status_code == 422


async def test_topic_permissions_and_isolation(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)

    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    assert (await viewer.get(f"{API}/{topic['id']}")).status_code == 200
    assert (await viewer.post(f"{API}/{topic['id']}/shortlist")).status_code == 403
    assert (await viewer.patch(f"{API}/{topic['id']}", json={"title": "x"})).status_code == 403
    assert (await designer.get(f"{API}/{topic['id']}")).status_code == 200
    assert (await manager.post(f"{API}/{topic['id']}/shortlist")).status_code == 200

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(f"{API}/{topic['id']}")).status_code == 404
    assert (await outsider.post(f"{API}/{topic['id']}/reject")).status_code == 404
    assert (await outsider.get(API)).json()["total"] == 0
    assert (await admin.get(f"{API}/{uuid.uuid4()}")).status_code == 404


async def test_backfill_creates_missing_topics(client, internet, fake_ai, db):
    admin, _ = await setup_org(client)
    await discover(admin)
    await db.execute(delete(TopicCandidate))
    await db.commit()
    assert (await admin.get(API, params={"status": "all"})).json()["total"] == 0

    assert await sync.backfill() == 1
    assert await sync.backfill() == 0  # idempotent
    assert (await gpt6_topic(admin))["status"] == "new"


# --- Platform recommendation --------------------------------------------------


def rules() -> dict:
    return {p: SimpleNamespace(platform=p, **DEFAULT_RULES[p]) for p in Platform}


def test_recommendation_is_explained():
    recommended, fit = recommend(
        RecommendationInput(
            enabled_platforms=["linkedin", "x", "instagram"],
            audience_text="CTOs and engineering leaders at B2B SaaS companies",
            topic_text="ai coding agents developers",
            sources=["hacker_news", "google_news"],
            angles=[{"title": "Agents in the SDLC", "platforms": ["linkedin"]}],
        ),
        rules(),
    )
    by_platform = {f["platform"]: f for f in fit}
    assert "facebook" not in by_platform  # not enabled
    assert recommended[0] == "linkedin" and fit[0]["platform"] == "linkedin"
    linkedin = by_platform["linkedin"]
    assert any(r.startswith("Fits your audience and goals: b2b") for r in linkedin["reasons"])
    assert any("Hacker News" in r for r in by_platform["x"]["reasons"])
    assert any("developers" in r for r in by_platform["x"]["reasons"])
    assert by_platform["instagram"]["reasons"] == ["Instagram is one of your active platforms"]
    assert "instagram" not in recommended
    assert all(0 <= f["score"] <= 100 for f in fit)


def test_recommendation_always_names_one_platform():
    recommended, fit = recommend(
        RecommendationInput(
            enabled_platforms=[], audience_text="", topic_text="", sources=[], angles=[]
        ),
        rules(),
    )
    assert len(fit) == len(Platform) and recommended == [fit[0]["platform"]]


def test_keyword_matching_respects_word_boundaries():
    _, fit = recommend(
        RecommendationInput(
            enabled_platforms=["linkedin"],
            audience_text="chrome extension users",  # contains "hr" inside a word
            topic_text="",
            sources=[],
            angles=[],
        ),
        rules(),
    )
    assert fit[0]["reasons"] == ["LinkedIn is one of your active platforms"]


# --- Platform playbooks -------------------------------------------------------


async def test_platform_rules_are_seeded_and_editable(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    rules_api = "/api/v1/platform-rules"

    listed = (await admin.get(rules_api)).json()
    assert [r["platform"] for r in listed] == ["linkedin", "x", "instagram", "facebook", "blog"]
    assert listed[0]["post_types"] == DEFAULT_RULES[Platform.LINKEDIN]["post_types"]

    resp = await admin.patch(
        f"{rules_api}/linkedin", json={"post_types": ["Founder story", "Carousel"], "tone": "Bold"}
    )
    assert resp.status_code == 200 and resp.json()["post_types"] == ["Founder story", "Carousel"]
    assert (await admin.patch(f"{rules_api}/linkedin", json={"post_types": []})).status_code == 422
    assert (await admin.patch(f"{rules_api}/tiktok", json={"tone": "x"})).status_code == 422

    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    assert (await designer.get(rules_api)).status_code == 200
    assert (await designer.patch(f"{rules_api}/x", json={"tone": "x"})).status_code == 403

    reset = (await admin.post(f"{rules_api}/linkedin/reset")).json()
    assert reset["post_types"] == DEFAULT_RULES[Platform.LINKEDIN]["post_types"]
    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    assert sum(e["action"] == "PLATFORM_RULES_UPDATED" for e in logs) == 2


# --- Content strategies -------------------------------------------------------


async def test_strategy_requires_a_shortlisted_topic(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)
    body = {"platform": "linkedin", "post_type": "Carousel"}
    resp = await admin.post(f"{API}/{topic['id']}/strategies", json=body)
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "Shortlist this topic before planning content for it."
    resp = await admin.post(f"{API}/{topic['id']}/strategies/suggest", json={"platform": "x"})
    assert resp.status_code == 409


async def test_strategy_lifecycle(client, internet, strategy_ai, db):
    admin, org = await setup_org(client)
    await discover(admin)
    topic = await shortlisted_topic(admin)
    base = f"{API}/{topic['id']}/strategies"

    suggestion = (await admin.post(f"{base}/suggest", json={"platform": "linkedin"})).json()
    assert suggestion["source"] == "ai" and suggestion["notice"] is None
    assert suggestion["post_type"] == "Carousel"  # from the playbook enum
    assert suggestion["objective"] == "Thought leadership"
    assert len(suggestion["recommended_format"]) == 60
    call = strategy_ai.calls[-1]
    assert "Carousel" in call["system"] and "Acme Software" in call["system"]
    assert "Claims to avoid: Acme is an OpenAI partner" in call["prompt"]
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "content_strategy"))
    template = await db.get(PromptTemplate, job.prompt_template_id)
    assert (template.name, template.version, job.status) == ("content_strategy", 1, "succeeded")

    fields = {k: v for k, v in suggestion.items() if k not in ("notice",)}
    created = await admin.post(base, json=fields)
    assert created.status_code == 201, created.text
    strategy = created.json()
    assert strategy["status"] == "draft" and strategy["source"] == "ai"
    assert strategy["created_by"] == admin.user["id"]

    # Post types are normalized to the playbook's spelling and validated.
    manual = await admin.post(base, json={"platform": "x", "post_type": "thread"})
    assert manual.status_code == 201 and manual.json()["post_type"] == "Thread"
    bad = await admin.post(base, json={"platform": "x", "post_type": "Carousel"})
    assert bad.status_code == 422
    assert bad.json()["error"]["details"][0]["field"] == "post_type"
    disabled = await admin.post(base, json={"platform": "instagram", "post_type": "Carousel"})
    assert disabled.status_code == 422
    assert disabled.json()["error"]["details"][0]["field"] == "platform"

    url = f"{base}/{strategy['id']}"
    edited = await admin.patch(url, json={"hook_direction": "Lead with a number."})
    assert edited.status_code == 200 and edited.json()["hook_direction"] == "Lead with a number."
    approved = (await admin.post(f"{url}/approve")).json()
    assert approved["status"] == "approved" and approved["approved_by"] == admin.user["id"]
    assert (await admin.patch(url, json={"tone": "Calm"})).status_code == 409
    reopened = (await admin.post(f"{url}/reopen")).json()
    assert reopened["status"] == "draft" and reopened["approved_at"] is None
    assert (await admin.patch(url, json={"tone": "Calm"})).json()["tone"] == "Calm"
    await admin.post(f"{url}/approve")

    detail = (await admin.get(f"{API}/{topic['id']}")).json()
    assert detail["strategy_count"] == 2 and detail["approved_strategy_count"] == 1
    listed = (await admin.get(API, params={"status": "shortlisted"})).json()["items"][0]
    assert listed["strategy_count"] == 2 and listed["approved_strategy_count"] == 1

    archived = (await admin.post(f"{base}/{manual.json()['id']}/archive")).json()
    assert archived["status"] == "archived"
    resp = await admin.post(f"{base}/{manual.json()['id']}/approve")
    assert resp.status_code == 409
    assert len((await admin.get(base)).json()) == 2
    assert (await admin.get(f"{API}/{topic['id']}")).json()["strategy_count"] == 1

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    actions = {e["action"] for e in logs}
    assert {"STRATEGY_CREATED", "STRATEGY_APPROVED", "STRATEGY_REOPENED"} <= actions


async def test_suggestion_falls_back_to_rules(client, internet, strategy_ai, db):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await shortlisted_topic(admin)
    strategy_ai.fail = AIError(AIErrorKind.RATE_LIMITED, "Gemini quota or rate limit reached.")

    resp = await admin.post(
        f"{API}/{topic['id']}/strategies/suggest", json={"platform": "linkedin"}
    )
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["source"] == "rules" and "rule-based draft" in draft["notice"]
    assert "Gemini" not in draft["notice"]
    assert draft["post_type"] in DEFAULT_RULES[Platform.LINKEDIN]["post_types"]
    assert draft["content_angle"].startswith("What GPT-6 changes for finance ops")
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "content_strategy"))
    assert job.status == "failed" and job.result["error_kind"] == "rate_limited"


async def test_rule_based_suggestion_without_ai(client, internet):
    admin, org = await setup_org(client)
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/brand",
        json={"tone": "Plain-spoken", "cta_guidelines": "Point to the free assessment."},
    )
    await discover(admin)
    topic = await shortlisted_topic(admin)
    draft = (
        await admin.post(f"{API}/{topic['id']}/strategies/suggest", json={"platform": "x"})
    ).json()
    assert draft["source"] == "rules" and draft["notice"] is None
    assert draft["tone"] == "Plain-spoken"
    assert draft["cta_direction"] == "Point to the free assessment."
    assert draft["post_type"] in DEFAULT_RULES[Platform.X]["post_types"]


async def test_strategy_permissions(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    topic = await shortlisted_topic(admin)
    base = f"{API}/{topic['id']}/strategies"
    created = (
        await admin.post(base, json={"platform": "linkedin", "post_type": "Carousel"})
    ).json()

    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.get(base)).status_code == 200
    assert (
        await viewer.post(base, json={"platform": "x", "post_type": "Thread"})
    ).status_code == 403
    assert (await viewer.post(f"{base}/{created['id']}/approve")).status_code == 403
    creator = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    assert (
        await creator.post(base, json={"platform": "x", "post_type": "Thread"})
    ).status_code == 201

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(base)).status_code == 404
    other_topic = f"{API}/{uuid.uuid4()}/strategies/{created['id']}/approve"
    assert (await admin.post(other_topic)).status_code == 404


async def test_remove_from_shortlist_also_unshortlists_the_trend(client, internet, fake_ai):
    admin, org = await setup_org(client)
    await discover(admin)
    topic = await shortlisted_topic(admin)
    removed = (await admin.post(f"{API}/{topic['id']}/review")).json()
    assert removed["status"] == "reviewed"
    trend = (await admin.get(f"/api/v1/trends/{topic['trend_id']}")).json()
    assert trend["status"] in ("new", "analyzed")


async def test_delete_topic_removes_it_and_its_trend(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await gpt6_topic(admin)
    # Only decided topics can be deleted.
    assert (await admin.delete(f"{API}/{topic['id']}")).status_code == 409
    topic = await shortlisted_topic(admin)

    assert (await admin.delete(f"{API}/{topic['id']}")).status_code == 204
    assert (await admin.get(f"{API}/{topic['id']}")).status_code == 404
    assert (await admin.get(f"/api/v1/trends/{topic['trend_id']}")).status_code == 404


async def test_delete_trend_removes_its_topic(client, internet, fake_ai):
    admin, _ = await setup_org(client)
    await discover(admin)
    topic = await shortlisted_topic(admin)
    trends = "/api/v1/trends"

    assert (await admin.delete(f"{trends}/{topic['trend_id']}")).status_code == 204
    assert (await admin.get(f"{trends}/{topic['trend_id']}")).status_code == 404
    assert (await admin.get(f"{API}/{topic['id']}")).status_code == 404
