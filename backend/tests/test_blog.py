"""Blog: long-form articles as a content platform alongside the social ones.
Same workflow (strategy → generation → versions → design → approval → final),
with its own playbook, SEO plan, prompts, output contract and checks."""

import pytest
from sqlalchemy import select

from app.ai.provider import StructuredResult, set_ai_provider
from app.models.ai import AIGenerationJob, PromptTemplate
from app.models.enums import Platform
from app.models.topic import TopicCandidate
from app.services.content import blog
from app.services.content.copy import InvalidCopy
from app.services.topics.platform_defaults import DEFAULT_RULES
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register
from tests.test_alignment import discover, internet, setup_org  # noqa: F401  (fixtures)
from tests.test_content import approved_strategy, generated
from tests.test_design import DesignAI, upload
from tests.test_topics import gpt6_topic

CONTENT = "/api/v1/content"

ARTICLE = {
    "seo_title": "GPT-6 Agents for Finance Teams: A Practical Guide",
    "meta_title": "GPT-6 Agents for Finance Teams: A Practical Guide to Faster Closes",
    "meta_description": "How GPT-6 agents cut reconciliation time for finance teams.",
    "slug": "  GPT-6 Agents: Finance Guide!! ",
    "keywords": ["GPT-6 agents", "finance automation", "GPT-6 agents"],
    "introduction": "Finance teams lose hours to reconciliation. GPT-6 agents change that.",
    "sections": [
        {"heading": "## What changed with GPT-6", "body": "Agents now handle multi-step work."},
        {"heading": "Practical steps", "body": "### Start small\n\n1. Pick one ledger."},
        {"heading": "Empty section", "body": "   "},
    ],
    "conclusion": "Agents are ready for finance work. Acme brings synergy.",
    "cta": "Book an AI Solutions workshop.",
    "featured_image": "A calm ledger turning into a checklist.",
    "evidence": ["K1", "K7"],
}


class BlogAI(DesignAI):
    """Also plans and writes blog articles, keyed on the blog-only schemas."""

    def __init__(self) -> None:
        super().__init__()
        self.articles = 0

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        props = schema.get("properties", {})
        if "Plan this topic" in prompt and "details" in props:
            self.calls.append({"system": system, "prompt": prompt, "schema": schema})
            data = {
                "post_type": "How-to guide",
                "objective": "Organic search traffic",
                "content_angle": "A step-by-step guide to agent-led reconciliation.",
                "target_audience": "Finance leaders",
                "hook_direction": "Open with the hours lost to reconciliation.",
                "cta_direction": "Invite readers to an AI Solutions workshop.",
                "tone": "Practical",
                "recommended_format": "1,500-word how-to guide",
                "rationale": "Searchers want a practical guide.",
                "details": {
                    "seo_title": "GPT-6 Agents for Finance: A Practical Guide",
                    "primary_keyword": "GPT-6 agents",
                    "secondary_keywords": ["finance automation", "", "finance automation"],
                    "search_intent": "Informational",
                    "outline": ["What changed", "Practical steps", "Examples"],
                    "target_word_count": 99_999,  # clamped
                    "featured_image_direction": "A ledger becoming a checklist.",
                },
            }
            return StructuredResult(
                data=data, model=self.model, input_tokens=600, output_tokens=200
            )
        if "sections" in props:
            self.calls.append({"system": system, "prompt": prompt, "schema": schema})
            self.articles += 1
            data = {**ARTICLE, "introduction": f"{ARTICLE['introduction']} (take {self.articles})"}
            return StructuredResult(
                data=data, model=self.model, input_tokens=3000, output_tokens=2500
            )
        return await super().generate_structured(
            system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
        )


@pytest.fixture
def blog_ai():
    ai = BlogAI()
    set_ai_provider(ai)
    yield ai
    set_ai_provider(None)


async def enable_blog(admin, org) -> None:
    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings",
        json={"enabled_platforms": ["linkedin", "x", "blog"]},
    )
    assert resp.status_code == 200, resp.text


async def blog_topic(admin, org) -> dict:
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/brand", json={"forbidden_terms": ["synergy"]}
    )
    await enable_blog(admin, org)
    await discover(admin)
    topic = await gpt6_topic(admin)
    await admin.post(f"/api/v1/topics/{topic['id']}/shortlist")
    return topic


PLAN = {
    "seo_title": "GPT-6 Agents for Finance Teams",
    "primary_keyword": "GPT-6 agents",
    "secondary_keywords": ["finance automation"],
    "search_intent": "informational",
    "outline": ["What changed", "Why it matters", "Practical steps"],
    "target_word_count": 1500,
    "featured_image_direction": "A ledger becoming a checklist.",
}


async def blog_strategy(admin, org) -> dict:
    """An approved Blog strategy with an SEO plan."""
    topic = await blog_topic(admin, org)
    base = f"/api/v1/topics/{topic['id']}/strategies"
    resp = await admin.post(
        base,
        json={
            "platform": "blog",
            "post_type": "how-to GUIDE",  # normalized to the playbook's spelling
            "content_angle": "Where agents beat manual reconciliation",
            "cta_direction": "Invite readers to an AI Solutions workshop",
            "details": PLAN,
        },
    )
    assert resp.status_code == 201, resp.text
    strategy = resp.json()
    assert (await admin.post(f"{base}/{strategy['id']}/approve")).status_code == 200
    return strategy


# --- Pure: playbook, plan, output contract and checks --------------------------------------


def test_blog_playbook_is_long_form_without_hashtags():
    rule = DEFAULT_RULES[Platform.BLOG]
    assert "How-to guide" in rule["post_types"] and rule["hashtag_limit"] == 0
    assert rule["max_length"] > DEFAULT_RULES[Platform.LINKEDIN]["max_length"]
    assert "Organic search traffic" in rule["objectives"]


def test_slugify():
    assert blog.slugify("  GPT-6 Agents: Finance Guide!! ") == "gpt-6-agents-finance-guide"
    assert blog.slugify("Café déjà vu") == "cafe-deja-vu"
    assert len(blog.slugify("word " * 40)) <= 80 and not blog.slugify("word " * 40).endswith("-")
    assert blog.slugify("!!!") == ""


def test_article_output_is_structured_and_cleaned():
    copy = blog.parse_output(ARTICLE, refs={"K1", "K2"})
    assert copy.hook.startswith("Finance teams lose hours")
    assert copy.body.startswith("## What changed with GPT-6\n\nAgents now handle")
    assert "## Practical steps\n\n### Start small" in copy.body
    assert "Empty section" not in copy.body  # sections without a body are dropped
    assert copy.body.endswith(
        "## Conclusion\n\nAgents are ready for finance work. Acme brings synergy."
    )
    assert copy.hashtags == [] and copy.design_format == "single_image"
    assert copy.visual_concept == "A calm ledger turning into a checklist."
    assert copy.evidence == ["K1"] and copy.corrections
    assert copy.blog == {
        "seo_title": "GPT-6 Agents for Finance Teams: A Practical Guide",
        "meta_title": "GPT-6 Agents for Finance Teams: A Practical Guide to Faster Closes",
        "meta_description": "How GPT-6 agents cut reconciliation time for finance teams.",
        "slug": "gpt-6-agents-finance-guide",
        "keywords": ["GPT-6 agents", "finance automation"],
    }
    with pytest.raises(InvalidCopy):
        blog.parse_output({**ARTICLE, "sections": []}, refs=set())
    with pytest.raises(InvalidCopy):
        blog.parse_output({**ARTICLE, "introduction": " "}, refs=set())


def test_blog_checks():
    copy = blog.parse_output(ARTICLE, refs=set())
    warnings = blog.check_blog(copy.blog, copy.hook, copy.body)
    assert any(w.startswith("About ") and "600+" in w for w in warnings)  # too short
    assert any(w.startswith("Meta title is 66 characters") for w in warnings)
    assert not any("primary keyword" in w for w in warnings)

    long_body = "## One\n\n" + "word " * 700
    good = {**copy.blog, "meta_title": "GPT-6 Agents for Finance"}
    assert blog.check_blog(good, "GPT-6 agents are here.", long_body) == []
    missing = blog.check_blog({}, "Intro", "No headings here")
    for expected in (
        "No section headings",
        "No SEO title.",
        "No meta title.",
        "No meta description.",
        "No URL slug.",
        "No target keywords.",
    ):
        assert any(w.startswith(expected) for w in missing), expected
    off_keyword = blog.check_blog({**good, "keywords": ["ledger close"]}, "Intro", long_body)
    assert off_keyword == ["The primary keyword “ledger close” isn't in the title or introduction."]


def test_plan_cleanup_and_rules_plan():
    plan = blog.clean_plan(
        {
            "seo_title": "x" * 500,
            "secondary_keywords": ["a", "", "a", "b"],
            "search_intent": "curious",
            "outline": [],
            "target_word_count": "lots",
        }
    )
    assert plan == {"seo_title": "x" * 120, "secondary_keywords": ["a", "b"]}
    assert blog.clean_plan("not a dict") == {}
    assert blog.clean_plan({"target_word_count": 10})["target_word_count"] == 300

    topic = TopicCandidate(title="GPT-6 agents", matched_services=["AI Solutions"])
    plan = blog.rules_plan(topic, ["gpt-6", "agents", "openai"], "finance leaders")
    assert plan["primary_keyword"] == "gpt-6" and plan["search_intent"] == "informational"
    assert plan["secondary_keywords"] == ["agents", "openai", "AI Solutions"]
    assert "Where AI Solutions fits in" in plan["outline"]
    assert plan["seo_title"].startswith("GPT-6 agents") and plan["target_word_count"] == 1500


# --- Platform validation and strategies ---------------------------------------------------


async def test_blog_platform_validation(client, internet):
    admin, org = await setup_org(client)  # enables LinkedIn and X only
    await discover(admin)
    topic = await gpt6_topic(admin)
    await admin.post(f"/api/v1/topics/{topic['id']}/shortlist")
    base = f"/api/v1/topics/{topic['id']}/strategies"
    body = {"platform": "blog", "post_type": "How-to guide"}

    resp = await admin.post(base, json=body)
    assert resp.status_code == 422 and "Blog isn't one of" in resp.json()["error"]["message"]
    await enable_blog(admin, org)
    rules = (await admin.get("/api/v1/platform-rules")).json()
    blog_rule = next(r for r in rules if r["platform"] == "blog")
    assert blog_rule["hashtag_limit"] == 0 and "Explainer" in blog_rule["post_types"]

    # Blog post types only; LinkedIn's "Carousel" isn't a blog format.
    resp = await admin.post(base, json={**body, "post_type": "Carousel"})
    assert resp.status_code == 422 and "Blog playbook" in resp.json()["error"]["message"]
    assert (await admin.post(base, json={**body, "platform": "medium"})).status_code == 422
    bad_plan = {**body, "details": {"target_word_count": 50}}
    assert (await admin.post(base, json=bad_plan)).status_code == 422
    bad_intent = {**body, "details": {"search_intent": "curious"}}
    assert (await admin.post(base, json=bad_intent)).status_code == 422

    # SEO plans belong to Blog strategies only.
    resp = await admin.post(
        base, json={"platform": "linkedin", "post_type": "Carousel", "details": PLAN}
    )
    assert resp.status_code == 422 and resp.json()["error"]["details"][0]["field"] == "details"
    linkedin = (
        await admin.post(base, json={"platform": "linkedin", "post_type": "Carousel"})
    ).json()
    assert linkedin["details"]["outline"] == [] and linkedin["details"]["seo_title"] is None

    created = (await admin.post(base, json={**body, "details": PLAN})).json()
    assert created["platform"] == "blog" and created["details"] == PLAN
    url = f"{base}/{created['id']}"
    edited = (await admin.patch(url, json={"details": {**PLAN, "outline": ["Only one"]}})).json()
    assert edited["details"]["outline"] == ["Only one"]
    # Switching to a social platform drops the SEO plan.
    switched = (
        await admin.patch(url, json={"platform": "linkedin", "post_type": "Carousel"})
    ).json()
    assert switched["platform"] == "linkedin" and switched["details"]["outline"] == []

    topics = (await admin.get("/api/v1/topics", params={"platform": "blog"})).json()
    assert topics["total"] >= 0  # the platform filter accepts blog


async def test_blog_strategy_suggestion_with_ai(client, internet, blog_ai, db):
    admin, org = await setup_org(client)
    topic = await blog_topic(admin, org)
    resp = await admin.post(
        f"/api/v1/topics/{topic['id']}/strategies/suggest", json={"platform": "blog"}
    )
    assert resp.status_code == 200, resp.text
    suggestion = resp.json()
    assert suggestion["source"] == "ai" and suggestion["post_type"] == "How-to guide"
    assert suggestion["details"] == {
        "seo_title": "GPT-6 Agents for Finance: A Practical Guide",
        "primary_keyword": "GPT-6 agents",
        "secondary_keywords": ["finance automation"],
        "search_intent": "informational",
        "outline": ["What changed", "Practical steps", "Examples"],
        "target_word_count": 6000,
        "featured_image_direction": "A ledger becoming a checklist.",
    }
    call = blog_ai.calls[-1]
    assert "strategy for covering it as a blog article" in call["system"]
    assert "Acme Software" in call["system"] and "Hashtags: none" in call["system"]
    assert "Plan this topic for Blog." in call["prompt"]
    assert "Search keywords from the trend:" in call["prompt"]
    assert "Claims to avoid: Acme is an OpenAI partner" in call["prompt"]
    assert (
        call["schema"]["properties"]["post_type"]["enum"]
        == DEFAULT_RULES[Platform.BLOG]["post_types"]
    )
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "content_strategy"))
    template = await db.get(PromptTemplate, job.prompt_template_id)
    assert template.name == "blog_strategy"

    # The suggestion saves as-is, plan included.
    saved = await admin.post(
        f"/api/v1/topics/{topic['id']}/strategies",
        json={k: v for k, v in suggestion.items() if k != "notice"},
    )
    assert saved.status_code == 201 and saved.json()["details"]["target_word_count"] == 6000


async def test_blog_strategy_rules_draft_without_ai(client, internet):
    admin, org = await setup_org(client)
    topic = await blog_topic(admin, org)
    suggestion = (
        await admin.post(
            f"/api/v1/topics/{topic['id']}/strategies/suggest", json={"platform": "blog"}
        )
    ).json()
    assert suggestion["source"] == "rules"
    assert suggestion["post_type"] in DEFAULT_RULES[Platform.BLOG]["post_types"]
    details = suggestion["details"]
    assert details["search_intent"] == "informational" and details["primary_keyword"]
    assert len(details["outline"]) >= 4 and details["seo_title"]
    assert details["featured_image_direction"]


# --- Content generation ------------------------------------------------------------------


async def test_blog_generation_is_grounded_long_form(client, internet, blog_ai, db):
    admin, org = await setup_org(client)
    strategy = await blog_strategy(admin, org)
    post = await generated(admin, strategy)

    assert post["platform"] == "blog" and post["status"] == "draft"
    assert post["generation"]["status"] == "succeeded" and post["generation"]["engine"] == "ai"
    assert post["limits"] == {"max_length": 20000, "hashtag_limit": 0}
    v1 = post["current"]
    assert v1["hook"].startswith("Finance teams lose hours") and v1["hashtags"] == []
    assert "## What changed with GPT-6" in v1["body"] and "## Conclusion" in v1["body"]
    meta = v1["meta"]
    assert meta["prompt"] == {"name": "blog_post", "version": 1}
    assert meta["blog"]["slug"] == "gpt-6-agents-finance-guide"
    assert meta["blog"]["keywords"] == ["GPT-6 agents", "finance automation"]
    assert meta["design_format"] == "single_image"
    assert meta["visual_concept"] == "A calm ledger turning into a checklist."
    # Grounded in the knowledge base, with citations limited to what was provided.
    assert meta["evidence"] == ["K1"] and meta["passages"][0]["title"] == "AI agents"
    assert "Uses the forbidden term “synergy”." in meta["warnings"]
    assert any(w.startswith("Meta title is") for w in meta["warnings"])

    call = blog_ai.calls[-1]
    assert "blog articles for Acme Software's website" in call["system"]
    assert "Acme Software" in call["system"] and "Hashtags: none" in call["system"]
    for expected in (
        "Platform: Blog",
        "Primary keyword: GPT-6 agents",
        "Search intent: informational",
        "Target length: about 1500 words",
        "Outline:\n- What changed\n- Why it matters\n- Practical steps",
        "Claims to avoid: Acme is an OpenAI partner",
        "Forbidden terms: synergy",
        'id="K1"',
        "Write the blog article.",
    ):
        assert expected in call["prompt"], expected
    assert "sections" in call["schema"]["properties"]
    assert "hashtags" not in call["schema"]["properties"]

    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    template = await db.get(PromptTemplate, job.prompt_template_id)
    assert template.name == "blog_post"
    listed = (await admin.get(CONTENT, params={"platform": "blog"})).json()
    assert listed["total"] == 1 and listed["items"][0]["platform"] == "blog"
    assert (await admin.get(CONTENT, params={"platform": "linkedin"})).json()["total"] == 0


async def test_blog_template_without_ai(client, internet):
    admin, org = await setup_org(client)
    post = await generated(admin, await blog_strategy(admin, org))
    v1 = post["current"]
    assert v1["meta"]["engine"] == "template" and v1["hashtags"] == []
    assert v1["body"].startswith("## What changed\n\nWhere agents beat manual reconciliation")
    assert "## Practical steps" in v1["body"] and "## Conclusion" in v1["body"]
    assert v1["cta"] == "Invite readers to an AI Solutions workshop"
    seo = v1["meta"]["blog"]
    assert seo["seo_title"] == PLAN["seo_title"] and seo["slug"] == "gpt-6-agents-for-finance-teams"
    assert seo["keywords"][:2] == ["GPT-6 agents", "finance automation"]
    assert v1["meta"]["visual_concept"] == PLAN["featured_image_direction"]
    assert any("600+" in w for w in v1["meta"]["warnings"])  # a skeleton, not an article


async def test_blog_edits_versions_regeneration_and_restore(client, internet, blog_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await blog_strategy(admin, org))
    url = f"{CONTENT}/{post['id']}"

    resp = await admin.patch(
        url,
        json={
            "base_version": 1,
            "blog": {"meta_title": "GPT-6 Agents for Finance", "slug": "gpt-6-finance"},
        },
    )
    assert resp.status_code == 200, resp.text
    v2 = resp.json()["current"]
    assert v2["version_number"] == 2 and v2["change_note"] == "Edited SEO details"
    assert v2["meta"]["blog"]["slug"] == "gpt-6-finance"
    # Fields not sent are kept.
    assert v2["meta"]["blog"]["meta_description"] == ARTICLE["meta_description"]
    assert not any(w.startswith("Meta title is") for w in v2["meta"]["warnings"])

    bad = await admin.patch(url, json={"base_version": 2, "blog": {"slug": "Not A Slug"}})
    assert bad.status_code == 422
    long_body = "## Section\n\n" + "word " * 5000  # beyond the old 20k-character cap
    resp = await admin.patch(url, json={"base_version": 2, "body": long_body})
    assert resp.status_code == 200 and resp.json()["current"]["version_number"] == 3

    resp = await admin.post(f"{url}/regenerate", json={"instructions": "Add a checklist"})
    assert resp.status_code == 202
    await runner.wait_idle()
    prompt = blog_ai.calls[-1]["prompt"]
    assert "<existing_version>" in prompt and "SEO title: GPT-6 Agents" in prompt
    assert "Introduction: Finance teams" in prompt
    assert "Rewrite the blog article following the editor's instructions." in prompt

    versions = (await admin.get(f"{url}/versions")).json()
    assert [v["version_number"] for v in versions] == [4, 3, 2, 1]
    assert versions[0]["meta"]["blog"]["slug"] == "gpt-6-agents-finance-guide"  # AI rewrote it
    v1 = versions[-1]
    assert v1["meta"]["blog"]["meta_title"] == ARTICLE["meta_title"]  # never edited in place

    restored = (await admin.post(f"{url}/versions/2/restore", json={"base_version": 4})).json()
    current = restored["current"]
    assert current["version_number"] == 5 and current["change_note"] == "Restored version 2"
    assert current["meta"]["blog"]["slug"] == "gpt-6-finance"

    variant = (await admin.post(f"{url}/variants")).json()
    await runner.wait_idle()
    variant = (await admin.get(f"{CONTENT}/{variant['id']}")).json()
    assert variant["platform"] == "blog" and variant["current"]["meta"]["blog"]
    assert "Write an alternative blog article" in blog_ai.calls[-1]["prompt"]


async def test_seo_fields_are_rejected_for_social_posts(client, internet, blog_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    resp = await admin.patch(
        f"{CONTENT}/{post['id']}", json={"base_version": 1, "blog": {"slug": "nope"}}
    )
    assert resp.status_code == 422 and resp.json()["error"]["details"][0]["field"] == "blog"


# --- Design, approval and final ----------------------------------------------------------


async def test_blog_design_approval_and_final(client, internet, blog_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await blog_strategy(admin, org))
    sent = (await admin.post(f"{CONTENT}/{post['id']}/send-to-design")).json()
    assert sent["status"] == "design_pending"
    await runner.wait_idle()
    brief_prompt = blog_ai.calls[-1]["prompt"]
    assert "the article's featured image" in brief_prompt
    assert "Write the design brief for this blog article." in brief_prompt

    task_url = f"/api/v1/design/tasks/{sent['design_task']['id']}"
    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    task = (await designer.get(task_url)).json()
    assert task["content"]["blog"]["slug"] == "gpt-6-agents-finance-guide"
    key = await upload(designer, task["id"], name="featured.png")
    await designer.post(
        f"{task_url}/assets", json={"files": [{"storage_key": key, "file_name": "featured.png"}]}
    )
    assert (await designer.post(f"{task_url}/submit")).status_code == 200

    queue = (await admin.get("/api/v1/approvals", params={"platform": "blog"})).json()
    assert queue["total"] == 1
    item = queue["items"][0]
    detail = (await admin.get(f"/api/v1/approvals/{item['id']}")).json()
    assert detail["content"]["meta"]["blog"]["seo_title"] == ARTICLE["seo_title"]
    url = f"/api/v1/approvals/{item['id']}"
    # Approving makes the post final in one click.
    assert (await admin.post(f"{url}/approve", json={})).json()["post"]["status"] == "final"


async def test_rules_brief_for_blog_uses_featured_image_and_seo(client, internet):
    admin, org = await setup_org(client)
    post = await generated(admin, await blog_strategy(admin, org))
    sent = (await admin.post(f"{CONTENT}/{post['id']}/send-to-design")).json()
    task = (await admin.get(f"/api/v1/design/tasks/{sent['design_task']['id']}")).json()
    assert task["format"] == "single_image" and task["dimensions"] == "1200×630 (1.91:1)"
    seo = post["current"]["meta"]["blog"]
    assert task["headline"] == seo["seo_title"]
    assert task["supporting_text"] == seo["meta_description"]
    assert task["slide_structure"] == []


# --- RBAC, tenant isolation and existing platforms -----------------------------------------


async def test_blog_permissions_and_isolation(client, internet, blog_ai):
    admin, org = await setup_org(client)
    strategy = await blog_strategy(admin, org)
    post = await generated(admin, strategy)
    url = f"{CONTENT}/{post['id']}"
    strategies = f"/api/v1/topics/{strategy['topic_id']}/strategies"

    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.get(url)).status_code == 200
    resp = await viewer.post(strategies, json={"platform": "blog", "post_type": "Explainer"})
    assert resp.status_code == 403
    resp = await viewer.patch(url, json={"base_version": 1, "blog": {"slug": "x"}})
    assert resp.status_code == 403
    creator = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    assert (
        await creator.patch("/api/v1/platform-rules/blog", json={"tone": "x"})
    ).status_code == 403  # the playbook is admin-only

    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    resp = await manager.patch(url, json={"base_version": 1, "blog": {"slug": "manager-slug"}})
    assert resp.status_code == 200
    assert resp.json()["current"]["created_by"] == manager.user["id"]

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(url)).status_code == 404
    assert (await outsider.patch(url, json={"base_version": 2, "blog": {}})).status_code == 404
    assert (await outsider.get(strategies)).status_code == 404
    assert (await outsider.get(CONTENT, params={"platform": "blog"})).json()["total"] == 0
    own_rules = (await outsider.get("/api/v1/platform-rules")).json()
    assert (
        next(r for r in own_rules if r["platform"] == "blog")["tone"]
        == (DEFAULT_RULES[Platform.BLOG]["tone"])
    )


async def test_existing_platforms_are_unaffected(client, internet, blog_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    v1 = post["current"]
    assert "blog" not in v1["meta"] and v1["meta"]["prompt"]["name"] == "linkedin_post"
    assert v1["hashtags"] and post["limits"] == {"max_length": 3000, "hashtag_limit": 5}
    assert post["strategy"]["details"]["outline"] == []
    call = blog_ai.calls[-1]
    assert "Write the LinkedIn post." in call["prompt"] and "Primary keyword" not in call["prompt"]
    assert "hashtags" in call["schema"]["properties"]
    assert "Hashtags: at most 5" in call["system"]


async def test_enabling_blog_rescores_existing_topics(client, internet):
    admin, org = await setup_org(client)  # LinkedIn and X only
    await discover(admin)
    topic = await gpt6_topic(admin)
    detail = (await admin.get(f"/api/v1/topics/{topic['id']}")).json()
    assert {f["platform"] for f in detail["platform_fit"]} == {"linkedin", "x"}

    await enable_blog(admin, org)
    detail = (await admin.get(f"/api/v1/topics/{topic['id']}")).json()
    assert "blog" in {f["platform"] for f in detail["platform_fit"]}
    blog_fit = next(f for f in detail["platform_fit"] if f["platform"] == "blog")
    assert blog_fit["formats"] == DEFAULT_RULES[Platform.BLOG]["post_types"][:3]
    # Blog is scored like any platform; the filter follows the recommendation.
    listed = (
        await admin.get("/api/v1/topics", params={"platform": "blog", "status": "all"})
    ).json()
    assert listed["total"] == int("blog" in detail["recommended_platforms"])
