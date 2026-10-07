"""Sprint 6: content generation, editing with versions, variants and the
draft → design hand-off (spec §23-26, §40, §56)."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.provider import (
    USER_MESSAGES,
    AIError,
    AIErrorKind,
    StructuredResult,
    set_ai_provider,
)
from app.models.ai import AIGenerationJob, PromptTemplate
from app.services.content.copy import check_copy, normalize_hashtags, parse_output
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register
from tests.test_alignment import discover, internet, setup_org  # noqa: F401  (fixtures)
from tests.test_topics import StrategyAI, gpt6_topic

API = "/api/v1/content"


class ContentAI(StrategyAI):
    """Also writes posts. Output is deliberately messy so validation shows."""

    def __init__(self) -> None:
        super().__init__()
        self.post_fail: AIError | None = None
        self.posts = 0

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        if "<strategy>" not in prompt:
            return await super().generate_structured(
                system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
            )
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if self.post_fail:
            raise self.post_fail
        self.posts += 1
        data = {
            "hook": f"Finance teams lose 20 hours a month to reconciliation (take {self.posts}).",
            "body": "GPT-6 agents change that. Acme builds them with synergy in mind.",
            "cta": "Book an AI Solutions workshop.",
            "hashtags": ["AI", "#ai", "finance ops", "#Automation", "#GPT6", "#Agents", "#Ops"],
            "visual_concept": "Slide 1: the 20-hour problem. Slide 2: the agent.",
            "design_format": "carousel",
            "evidence": ["K1", "K9"],
        }
        return StructuredResult(data=data, model=self.model, input_tokens=1200, output_tokens=300)


@pytest.fixture
def content_ai():
    ai = ContentAI()
    set_ai_provider(ai)
    yield ai
    set_ai_provider(None)


async def approved_strategy(admin, org, platform: str = "linkedin") -> dict:
    """Org with a forbidden term, a shortlisted GPT-6 topic and an approved strategy."""
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/brand", json={"forbidden_terms": ["synergy"]}
    )
    await discover(admin)
    topic = await gpt6_topic(admin)
    await admin.post(f"/api/v1/topics/{topic['id']}/shortlist")
    base = f"/api/v1/topics/{topic['id']}/strategies"
    strategy = (
        await admin.post(
            base,
            json={
                "platform": platform,
                "post_type": "Carousel" if platform == "linkedin" else "Short insight",
                "content_angle": "Where agents beat manual reconciliation",
                "cta_direction": "Invite readers to an AI Solutions workshop",
            },
        )
    ).json()
    await admin.post(f"{base}/{strategy['id']}/approve")
    return strategy


async def generated(admin, strategy: dict) -> dict:
    resp = await admin.post(f"{API}/generate", json={"strategy_id": strategy["id"]})
    assert resp.status_code == 202, resp.text
    assert resp.json()["generation"]["status"] in ("queued", "running", "succeeded")
    await runner.wait_idle()
    return (await admin.get(f"{API}/{resp.json()['id']}")).json()


# --- Pure validation ----------------------------------------------------------------


def test_hashtags_are_normalized_and_capped():
    tags, notes = normalize_hashtags(["AI", "#ai", "finance ops", "#Ok!", "#B", "#C"], 3)
    assert tags == ["#AI", "#financeops", "#B"]
    assert any("invalid" in n for n in notes) and any("first 3" in n for n in notes)


def test_output_requires_hook_and_body_and_filters_citations():
    copy = parse_output(
        {
            "hook": "H",
            "body": "B",
            "cta": "",
            "hashtags": [],
            "evidence": ["K1", "K7"],
            "design_format": "hologram",
        },
        refs={"K1"},
        hashtag_limit=5,
    )
    assert copy.evidence == ["K1"] and copy.design_format is None
    with pytest.raises(ValueError):
        parse_output({"hook": "", "body": "B"}, refs=set(), hashtag_limit=None)


def test_checks_flag_forbidden_terms_length_and_missing_cta():
    warnings = check_copy(
        hook="Big news",
        body="Pure Synergy " * 30,
        cta="",
        hashtags=["#A", "#B", "#C"],
        forbidden_terms=["synergy", "unused"],
        max_length=280,
        hashtag_limit=2,
        platform_label="X",
    )
    assert warnings[0] == "Uses the forbidden term “synergy”."
    assert "over the X limit of 280" in warnings[1]
    assert warnings[2] == "3 hashtags; the playbook allows 2."
    assert warnings[3] == "No call to action."


# --- Generation ---------------------------------------------------------------------


async def test_generate_post_from_approved_strategy(client, internet, content_ai, db):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    post = await generated(admin, strategy)

    assert post["status"] == "draft" and post["platform"] == "linkedin"
    assert post["current_version"] == 1 and post["editable"] is True
    assert post["topic"]["title"].lower().startswith("gpt-6")
    assert post["generation"]["status"] == "succeeded" and post["generation"]["engine"] == "ai"
    assert post["limits"] == {"max_length": 3000, "hashtag_limit": 5}
    v1 = post["current"]
    assert v1["hook"].startswith("Finance teams lose 20 hours") and v1["source"] == "ai"
    assert v1["hashtags"] == ["#AI", "#financeops", "#Automation", "#GPT6", "#Agents"]
    assert v1["meta"]["evidence"] == ["K1"]  # K9 was never provided
    assert v1["meta"]["passages"][0]["title"] == "AI agents"  # grounded in the knowledge base
    assert (
        v1["meta"]["visual_concept"].startswith("Slide 1")
        and v1["meta"]["design_format"] == "carousel"
    )
    assert v1["meta"]["warnings"] == ["Uses the forbidden term “synergy”."]
    assert v1["meta"]["prompt"] == {"name": "linkedin_post", "version": 1}
    assert v1["created_by"] == admin.user["id"]

    call = content_ai.calls[-1]
    assert "LinkedIn posts for Acme Software" in call["system"]
    assert "Where agents beat manual reconciliation" in call["prompt"]
    assert "Claims to avoid: Acme is an OpenAI partner" in call["prompt"]
    assert "Forbidden terms: synergy" in call["prompt"]
    assert 'id="K1"' in call["prompt"]

    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "post_generation"))
    template = await db.get(PromptTemplate, job.prompt_template_id)
    assert (template.name, job.input_tokens, job.status) == ("linkedin_post", 1200, "succeeded")

    listed = (await admin.get(API)).json()
    assert listed["total"] == 1 and listed["counts"]["drafts"] == 1
    assert listed["items"][0]["hook"] == v1["hook"]
    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["drafts"] == 1


async def test_platform_specific_prompt(client, internet, content_ai):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org, platform="x")
    post = await generated(admin, strategy)
    assert "posts for X (Twitter)" in content_ai.calls[-1]["system"]
    assert post["current"]["meta"]["prompt"]["name"] == "x_post"
    assert len(post["current"]["hashtags"]) == 2  # X playbook limit


async def test_writing_a_post_from_a_draft_plan_approves_the_plan(client, internet, content_ai):
    """No separate approval click: "Write post" on a draft plan approves it."""
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    topic_url = f"/api/v1/topics/{strategy['topic_id']}/strategies/{strategy['id']}"
    await admin.post(f"{topic_url}/reopen")
    resp = await admin.post(f"{API}/generate", json={"strategy_id": strategy["id"]})
    assert resp.status_code == 202, resp.text
    await runner.wait_idle()
    plans = (await admin.get(f"/api/v1/topics/{strategy['topic_id']}/strategies")).json()
    assert {p["id"]: p["status"] for p in plans}[strategy["id"]] == "approved"

    await admin.post(f"{topic_url}/archive")
    resp = await admin.post(f"{API}/generate", json={"strategy_id": strategy["id"]})
    assert resp.status_code == 409  # archived plans can't be written from
    resp = await admin.post(f"{API}/generate", json={"strategy_id": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_template_draft_without_ai(client, internet):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    post = await generated(admin, strategy)
    v1 = post["current"]
    assert post["generation"]["engine"] == "template" and v1["meta"]["engine"] == "template"
    assert v1["hook"] and v1["body"].startswith("Where agents beat manual reconciliation")
    assert "[K" not in v1["body"]  # citation markers are stripped
    assert v1["cta"] == "Invite readers to an AI Solutions workshop"


async def test_ai_failure_is_recorded_and_retry_works(client, internet, content_ai):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    content_ai.post_fail = AIError(AIErrorKind.UNAVAILABLE, "Gemini error (503).")
    post = await generated(admin, strategy)
    assert post["current_version"] == 0 and post["current"] is None
    assert post["generation"]["status"] == "failed"
    assert post["generation"]["error"] == USER_MESSAGES[AIErrorKind.UNAVAILABLE]

    content_ai.post_fail = None
    resp = await admin.post(f"{API}/{post['id']}/regenerate", json={})
    assert resp.status_code == 202
    await runner.wait_idle()
    post = (await admin.get(f"{API}/{post['id']}")).json()
    assert post["current_version"] == 1 and post["generation"]["status"] == "succeeded"


async def test_regenerate_keeps_old_versions_and_passes_instructions(client, internet, content_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    resp = await admin.post(
        f"{API}/{post['id']}/regenerate", json={"instructions": "Shorter, lead with the number"}
    )
    assert resp.status_code == 202
    await runner.wait_idle()

    prompt = content_ai.calls[-1]["prompt"]
    assert "<editor_instructions>\nShorter, lead with the number" in prompt
    assert "<existing_version>" in prompt and "take 1" in prompt

    versions = (await admin.get(f"{API}/{post['id']}/versions")).json()
    assert [v["version_number"] for v in versions] == [2, 1]
    assert "take 2" in versions[0]["hook"] and "take 1" in versions[1]["hook"]
    assert versions[0]["change_note"] == "Regenerated with instructions"
    assert versions[0]["meta"]["instructions"] == "Shorter, lead with the number"


# --- Editing and versions ------------------------------------------------------------------


async def test_edits_create_versions_and_never_overwrite(client, internet, content_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    url = f"{API}/{post['id']}"

    edited = await admin.patch(
        url,
        json={
            "base_version": 1,
            "hook": "A sharper hook.",
            "body": "No forbidden words here.",
            "hashtags": ["#AI"],
            "visual_concept": "One bold chart.",
        },
    )
    assert edited.status_code == 200, edited.text
    v2 = edited.json()["current"]
    assert edited.json()["current_version"] == 2 and v2["source"] == "manual"
    assert v2["hook"] == "A sharper hook." and v2["cta"] == "Book an AI Solutions workshop."
    assert v2["meta"]["visual_concept"] == "One bold chart."
    assert v2["meta"]["design_format"] == "carousel"  # carried over
    assert v2["meta"]["warnings"] == [] and v2["meta"]["edited_from"] == 1
    assert "prompt" not in v2["meta"]  # a person wrote this version
    assert v2["change_note"] == "Edited hook, body, hashtags, visual concept"

    # A stale editor can't overwrite the newer version.
    stale = await admin.patch(url, json={"base_version": 1, "hook": "Old tab"})
    assert stale.status_code == 409 and "version 2" in stale.json()["error"]["message"]
    # Saving without changes adds nothing; a title change doesn't need a version.
    same = await admin.patch(url, json={"base_version": 2, "hook": "A sharper hook."})
    assert same.json()["current_version"] == 2
    titled = await admin.patch(url, json={"base_version": 2, "title": "GPT-6 carousel"})
    assert titled.json()["title"] == "GPT-6 carousel" and titled.json()["current_version"] == 2

    restored = await admin.post(f"{url}/versions/1/restore", json={"base_version": 2})
    assert restored.status_code == 200
    v3 = restored.json()["current"]
    assert v3["version_number"] == 3 and v3["hook"] == post["current"]["hook"]
    assert v3["change_note"] == "Restored version 1"
    assert v3["meta"]["warnings"] == ["Uses the forbidden term “synergy”."]
    versions = (await admin.get(f"{url}/versions")).json()
    assert [v["hook"] for v in versions][1] == "A sharper hook."  # v2 untouched
    assert (
        await admin.post(f"{url}/versions/3/restore", json={"base_version": 3})
    ).status_code == 409
    assert (
        await admin.post(f"{url}/versions/9/restore", json={"base_version": 3})
    ).status_code == 404


async def test_variants_are_grouped(client, internet, content_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    resp = await admin.post(f"{API}/{post['id']}/variants")
    assert resp.status_code == 202
    variant_id = resp.json()["id"]
    await runner.wait_idle()

    variant = (await admin.get(f"{API}/{variant_id}")).json()
    assert variant["variant_of_id"] == post["id"] and variant["current_version"] == 1
    assert variant["current"]["change_note"] == "Generated as a variant"
    assert "<existing_version>" in content_ai.calls[-1]["prompt"]
    assert "clearly different hook" in content_ai.calls[-1]["prompt"]
    assert [v["id"] for v in variant["variants"]] == [post["id"]]

    # A variant of a variant joins the same group.
    third = (await admin.post(f"{API}/{variant_id}/variants")).json()
    await runner.wait_idle()
    original = (await admin.get(f"{API}/{post['id']}")).json()
    assert {v["id"] for v in original["variants"]} == {variant_id, third["id"]}
    assert third["variant_of_id"] == post["id"]


# --- Workflow ----------------------------------------------------------------------------


async def test_review_and_hand_off_to_design(client, internet, content_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    url = f"{API}/{post['id']}"

    # The "In review" step (no reviewer) is gone.
    assert (await admin.post(f"{url}/submit-review")).status_code in (404, 405)

    sent = (await admin.post(f"{url}/send-to-design")).json()
    assert sent["status"] == "design_pending"
    # A typo found during design can still be fixed without leaving design.
    assert sent["editable"] is True
    fixed = await admin.patch(url, json={"base_version": 1, "hook": "Fixed a typo"})
    assert fixed.status_code == 200 and fixed.json()["status"] == "design_pending"
    listed = (await admin.get(API, params={"status": "design"})).json()
    assert [p["id"] for p in listed["items"]] == [post["id"]]

    back = (await admin.post(f"{url}/back-to-draft")).json()
    assert back["status"] == "draft"
    archived = (await admin.post(f"{url}/archive")).json()
    assert archived["status"] == "archived"

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    actions = [e["action"] for e in logs]
    assert "CONTENT_GENERATED" in actions and "STATUS_CHANGED" in actions


async def test_empty_post_cant_move_on(client, internet, content_ai):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    content_ai.post_fail = AIError(AIErrorKind.RATE_LIMITED, "quota")
    post = await generated(admin, strategy)
    resp = await admin.post(f"{API}/{post['id']}/send-to-design")
    assert resp.status_code == 409


async def test_filters(client, internet, content_ai):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    for params, expected in [
        ({"status": "all"}, 1),
        ({"status": "design"}, 0),
        ({"platform": "linkedin"}, 1),
        ({"platform": "x"}, 0),
        ({"topic_id": post["topic"]["id"]}, 1),
        ({"q": "reconciliation"}, 1),  # matches the copy, not just the title
        ({"q": "nothing like this"}, 0),
    ]:
        assert (await admin.get(API, params=params)).json()["total"] == expected, params


async def test_content_permissions_and_isolation(client, internet, content_ai):
    admin, org = await setup_org(client)
    strategy = await approved_strategy(admin, org)
    post = await generated(admin, strategy)
    url = f"{API}/{post['id']}"

    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.get(url)).status_code == 200
    assert (await viewer.get(f"{url}/versions")).status_code == 200
    assert (await viewer.patch(url, json={"base_version": 1, "hook": "x"})).status_code == 403
    assert (await viewer.post(f"{url}/regenerate", json={})).status_code == 403
    assert (
        await viewer.post(f"{API}/generate", json={"strategy_id": strategy["id"]})
    ).status_code == 403

    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    resp = await manager.patch(url, json={"base_version": 1, "hook": "Manager edit"})
    assert resp.status_code == 200 and resp.json()["current"]["created_by"] == manager.user["id"]

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(url)).status_code == 404
    assert (
        await outsider.post(f"{API}/generate", json={"strategy_id": strategy["id"]})
    ).status_code == 404
    assert (await outsider.get(API)).json()["total"] == 0
