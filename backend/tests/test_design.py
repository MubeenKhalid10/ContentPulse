"""Sprint 7: design briefs, designer tasks, signed uploads and creative
versions (spec §27-30, §41, §52)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from botocore.stub import Stubber
from sqlalchemy import select

from app.ai.provider import AIError, AIErrorKind, StructuredResult, set_ai_provider
from app.models.ai import AIGenerationJob, LLMRequest
from app.models.design import DesignBrief
from app.services.design import briefs
from app.storage import safe_filename
from app.storage.s3 import S3Storage
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_content import ContentAI, approved_strategy, generated
from tests.test_topics import gpt6_topic

API = "/api/v1/design/tasks"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class DesignAI(ContentAI):
    """Also writes design briefs."""

    def __init__(self) -> None:
        super().__init__()
        self.brief_fail: AIError | None = None

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        if "Write the design brief" not in prompt:
            return await super().generate_structured(
                system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
            )
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if self.brief_fail:
            raise self.brief_fail
        data = {
            "format": "carousel",
            "dimensions": "1080×1350 (4:5)",
            "visual_concept": "Clean B2B look, one big number per slide.",
            "headline": "20 hours a month, gone",
            "supporting_text": "What GPT-6 agents do for finance teams",
            "slide_structure": [
                "Slide 1: 20 hours",
                "Slide 2: The agent",
                "Slide 3: Book a workshop",
            ],
            "visual_elements": ["Clock icon", "Simple bar chart"],
            "designer_notes": "No stock photos of robots.",
        }
        return StructuredResult(data=data, model=self.model, input_tokens=400, output_tokens=150)


@pytest.fixture
def design_ai():
    ai = DesignAI()
    set_ai_provider(ai)
    yield ai
    set_ai_provider(None)


async def in_design(admin, org) -> tuple[dict, dict]:
    """A generated LinkedIn post sent to design; returns (post, task)."""
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/brand",
        json={"brand_colors": ["#0F766E", "#111827"], "typography": "Inter"},
    )
    post = await generated(admin, await approved_strategy(admin, org))
    sent = (await admin.post(f"/api/v1/content/{post['id']}/send-to-design")).json()
    await runner.wait_idle()  # the AI brief, when configured
    task = (await admin.get(f"{API}/{sent['design_task']['id']}")).json()
    return post, task


async def upload(
    actor,
    task_id: str,
    name: str = "slide-1.png",
    data: bytes = PNG,
    content_type: str = "image/png",
) -> str:
    ticket = await actor.post(
        f"{API}/{task_id}/uploads",
        json={"file_name": name, "file_type": content_type, "file_size": len(data)},
    )
    assert ticket.status_code == 200, ticket.text
    t = ticket.json()
    assert t["method"] == "PUT" and t["url"].startswith("/api/v1/storage/local/")
    # The browser sends the file straight to the signed URL, without a session.
    resp = await actor.client.put(t["url"], content=data, headers=t["headers"])
    assert resp.status_code == 200, resp.text
    return t["storage_key"]


# --- Briefs -------------------------------------------------------------------------------


async def test_rule_based_brief_when_sent_to_design(client, internet, design_ai):
    admin, org = await setup_org(client)
    design_ai.brief_fail = AIError(AIErrorKind.UNAVAILABLE, "Gemini error (503).")
    post, task = await in_design(admin, org)

    assert task["status"] == "open" and task["source"] == "rules"
    assert task["post"]["status"] == "design_pending" and task["post"]["platform"] == "linkedin"
    assert task["format"] == "carousel" and task["dimensions"].startswith("1080×1350")
    assert task["headline"] == post["current"]["hook"]
    assert task["supporting_text"].startswith("GPT-6 agents change that.")
    assert task["slide_structure"] == ["Slide 1: the 20-hour problem.", "Slide 2: the agent."]
    assert task["cta"] == "Book an AI Solutions workshop."
    req = task["brand_requirements"]
    assert req["colors"] == ["#0F766E", "#111827"] and req["typography"] == "Inter"
    assert req["avoid_terms"] == ["synergy"] and req["logo"] is True
    assert task["content"]["version"] == 1 and task["content"]["hashtags"]
    assert task["brand"]["colors"] == ["#0F766E", "#111827"]
    assert task["creatives"] == [] and task["storage"] == "local" and not task["ai_brief_pending"]

    page = (await admin.get(API)).json()
    assert page["total"] == 1 and page["counts"]["todo"] == 1
    assert page["items"][0]["post"]["topic_title"].lower().startswith("gpt-6")
    detail = (await admin.get(f"/api/v1/content/{post['id']}")).json()
    assert detail["design_task"] == {"id": task["id"], "status": "open"}


async def test_ai_brief_replaces_rules_brief(client, internet, design_ai, db):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    assert task["source"] == "ai" and task["headline"] == "20 hours a month, gone"
    assert task["slide_structure"][0] == "Slide 1: 20 hours"
    assert task["visual_elements"] == ["Clock icon", "Simple bar chart"]
    assert task["designer_notes"] == "No stock photos of robots."
    assert task["brand_requirements"]["colors"] == ["#0F766E", "#111827"]  # still from the DB
    assert "LinkedIn" in design_ai.calls[-1]["prompt"]
    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "design_brief"))
    assert job.status == "succeeded" and job.result == {"applied": True}


async def test_ai_never_overwrites_an_edited_brief(client, internet, design_ai, db):
    admin, org = await setup_org(client)
    design_ai.brief_fail = AIError(AIErrorKind.UNAVAILABLE, "down")
    _, task = await in_design(admin, org)
    edited = await admin.patch(
        f"{API}/{task['id']}", json={"headline": "Our headline", "slide_structure": None}
    )
    assert edited.status_code == 200
    assert edited.json()["source"] == "edited" and edited.json()["slide_structure"] == []

    design_ai.brief_fail = None
    brief = await db.get(DesignBrief, uuid.UUID(task["id"]))
    job = AIGenerationJob(
        organization_id=brief.organization_id,
        type=briefs.JOB_TYPE,
        entity_type="design_brief",
        entity_id=brief.id,
    )
    db.add(job)
    await db.commit()
    await briefs.run_ai_brief(job.id)
    after = (await admin.get(f"{API}/{task['id']}")).json()
    assert after["headline"] == "Our headline" and after["source"] == "edited"


async def test_back_to_draft_cancels_and_resend_keeps_designer(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, task = await in_design(admin, org)
    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    await designer.post(f"{API}/{task['id']}/assign", json={"assignee_id": designer.user["id"]})

    await admin.post(f"/api/v1/content/{post['id']}/back-to-draft")
    assert (await admin.get(f"{API}/{task['id']}")).json()["status"] == "cancelled"
    assert (await admin.get(API)).json()["counts"]["cancelled"] == 1

    resent = (await admin.post(f"/api/v1/content/{post['id']}/send-to-design")).json()
    new_task = (await admin.get(f"{API}/{resent['design_task']['id']}")).json()
    assert new_task["id"] != task["id"]
    assert new_task["status"] == "assigned" and new_task["assignee"]["id"] == designer.user["id"]


# --- Designer flow --------------------------------------------------------------------


async def test_designer_takes_uploads_versions_and_submits(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, task = await in_design(admin, org)
    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    url = f"{API}/{task['id']}"

    mine = (await designer.get(API, params={"mine": "true"})).json()
    assert mine["total"] == 0
    taken = (await designer.post(f"{url}/assign", json={"assignee_id": designer.user["id"]})).json()
    assert taken["status"] == "assigned" and taken["assignee"]["email"] == "dee@acme.example.com"
    assert (await designer.get(API, params={"mine": "true"})).json()["total"] == 1

    started = (await designer.post(f"{url}/start")).json()
    assert started["status"] == "in_progress" and started["post"]["status"] == "design_in_progress"

    key = await upload(designer, task["id"])
    assert key.startswith(f"orgs/{org['id']}/posts/{post['id']}/briefs/{task['id']}/")
    v1 = await designer.post(
        f"{url}/assets",
        json={"files": [{"storage_key": key, "file_name": "Slide 1.png"}], "note": "First pass"},
    )
    assert v1.status_code == 200, v1.text
    body = v1.json()
    assert body["post"]["status"] == "design_uploaded" and body["creative_versions"] == 1
    [version] = body["creatives"]
    assert version["version"] == 1 and version["note"] == "First pass"
    assert version["uploaded_by"]["id"] == designer.user["id"]
    [file] = version["files"]
    assert file["file_type"] == "image/png" and file["file_size"] == len(PNG)

    # Signed links serve the file without a session.
    viewed = await client.get(file["url"])
    assert viewed.status_code == 200 and viewed.content == PNG
    assert viewed.headers["content-type"] == "image/png"
    downloaded = await client.get(file["download_url"])
    assert downloaded.headers["content-disposition"].startswith("attachment")

    # A revision is a new version; version 1 stays.
    keys = [await upload(designer, task["id"], f"slide-{i}.png") for i in (1, 2)]
    v2 = (
        await designer.post(
            f"{url}/assets",
            json={
                "files": [
                    {"storage_key": k, "file_name": f"Slide {i}.png"} for i, k in enumerate(keys, 1)
                ]
            },
        )
    ).json()
    assert [v["version"] for v in v2["creatives"]] == [2, 1]
    assert [f["position"] for f in v2["creatives"][0]["files"]] == [0, 1]

    submitted = (await designer.post(f"{url}/submit")).json()
    assert submitted["status"] == "submitted" and submitted["submitted_at"]
    assert submitted["post"]["status"] == "pending_approval"
    assert (await designer.post(f"{url}/submit")).status_code == 409
    resp = await designer.post(
        f"{url}/uploads", json={"file_name": "late.png", "file_type": "image/png", "file_size": 10}
    )
    assert resp.status_code == 409
    assert (await admin.get(API, params={"status": "submitted"})).json()["total"] == 1

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    actions = [e["action"] for e in logs]
    assert {"DESIGN_TASK_ASSIGNED", "DESIGN_UPLOADED", "APPROVAL_REQUESTED"} <= set(actions)


async def test_uploading_claims_an_unassigned_task(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    key = await upload(designer, task["id"])
    body = (
        await designer.post(
            f"{API}/{task['id']}/assets",
            json={"files": [{"storage_key": key, "file_name": "a.png"}]},
        )
    ).json()
    assert body["assignee"]["id"] == designer.user["id"]
    # Straight from design_pending to design_uploaded.
    assert body["post"]["status"] == "design_uploaded"


async def test_submit_requires_an_upload(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    resp = await admin.post(f"{API}/{task['id']}/submit")
    assert resp.status_code == 409
    assert (
        resp.json()["error"]["message"] == "Upload the creative before submitting it for approval."
    )


async def test_upload_validation(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    url = f"{API}/{task['id']}"

    bad_type = await admin.post(
        f"{url}/uploads",
        json={"file_name": "notes.txt", "file_type": "text/plain", "file_size": 10},
    )
    assert bad_type.status_code == 400 and bad_type.json()["error"]["code"] == "FILE_UPLOAD_FAILED"
    too_big = await admin.post(
        f"{url}/uploads",
        json={"file_name": "huge.mp4", "file_type": "video/mp4", "file_size": 101_000_000},
    )
    assert too_big.status_code == 400 and "100 MB" in too_big.json()["error"]["message"]
    guessed = await admin.post(f"{url}/uploads", json={"file_name": "deck.pdf", "file_size": 10})
    assert (
        guessed.status_code == 200
        and guessed.json()["headers"]["Content-Type"] == "application/pdf"
    )

    ticket = (
        await admin.post(
            f"{url}/uploads", json={"file_name": "a.png", "file_type": "image/png", "file_size": 10}
        )
    ).json()
    wrong_type = await client.put(
        ticket["url"], content=PNG, headers={"Content-Type": "image/jpeg"}
    )
    assert wrong_type.status_code == 400
    empty = await client.put(ticket["url"], content=b"", headers=ticket["headers"])
    assert empty.status_code == 400
    forged = await client.put(ticket["url"][:-4] + "abcd", content=PNG, headers=ticket["headers"])
    assert forged.status_code == 403
    download_token_misuse = await client.get(ticket["url"])
    assert download_token_misuse.status_code == 403  # an upload link can't read files

    never_uploaded = await admin.post(
        f"{url}/assets",
        json={"files": [{"storage_key": ticket["storage_key"], "file_name": "a.png"}]},
    )
    assert (
        never_uploaded.status_code == 400
        and "didn't finish uploading" in never_uploaded.json()["error"]["message"]
    )
    foreign = await admin.post(
        f"{url}/assets",
        json={"files": [{"storage_key": f"orgs/{uuid.uuid4()}/x.png", "file_name": "x.png"}]},
    )
    assert foreign.status_code == 400
    escape = await admin.post(
        f"{url}/assets",
        json={"files": [{"storage_key": ticket["storage_key"] + "/../../x", "file_name": "x"}]},
    )
    assert escape.status_code == 400


# --- Permissions --------------------------------------------------------------------


async def test_design_permissions(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    url = f"{API}/{task['id']}"
    dee = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    dan = await add_member(client, admin, org["id"], "dan@acme.example.com", "creator")
    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")

    assert (await viewer.get(url)).status_code == 200
    assert (await viewer.post(f"{url}/start")).status_code == 403
    # Creators edit the brief and deliver designs; only admins hand out work.
    assert (await manager.patch(url, json={"designer_notes": "Bold"})).status_code == 200
    assert (
        await manager.post(
            f"{url}/uploads", json={"file_name": "a.png", "file_type": "image/png", "file_size": 5}
        )
    ).status_code == 200
    assert (
        await dee.post(f"{url}/assign", json={"assignee_id": dan.user["id"]})
    ).status_code == 403
    # Admins assign; only designers (people who can upload) are valid assignees.
    assert (
        await admin.post(f"{url}/assign", json={"assignee_id": viewer.user["id"]})
    ).status_code == 422
    assigned = await admin.post(f"{url}/assign", json={"assignee_id": dee.user["id"]})
    assert assigned.status_code == 200
    # Creators can't take a task from someone else, but anyone may deliver on
    # it: the assignee shows who's on it, it doesn't lock teammates out.
    assert (
        await dan.post(f"{url}/assign", json={"assignee_id": dan.user["id"]})
    ).status_code == 403
    assert (
        await dan.post(
            f"{url}/uploads", json={"file_name": "a.png", "file_type": "image/png", "file_size": 5}
        )
    ).status_code == 200
    unassigned = (await admin.post(f"{url}/assign", json={"assignee_id": None})).json()
    assert unassigned["status"] == "open" and unassigned["assignee"] is None

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(url)).status_code == 404
    assert (await outsider.get(API)).json()["total"] == 0


# --- Storage ------------------------------------------------------------------------


def test_safe_filenames():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("Final Slide (v2).PNG") == "final-slide-v2.png"
    assert safe_filename("C:\\Users\\me\\deck.pdf") == "deck.pdf"


async def test_s3_presigned_urls_and_head():
    settings = SimpleNamespace(
        s3_bucket="cp-creatives",
        signed_url_ttl_seconds=600,
        aws_region="eu-west-1",
        s3_endpoint_url=None,
        aws_access_key_id="AKIAEXAMPLE",
        aws_secret_access_key="secret",
    )
    storage = S3Storage(settings)
    target = await storage.upload_target("orgs/1/a.png", "image/png", 1000)
    assert target.url.startswith("https://cp-creatives.s3.") and "X-Amz-Signature=" in target.url
    assert target.headers == {"Content-Type": "image/png"} and target.expires_at > datetime.now(UTC)
    download = await storage.download_url("orgs/1/a.png", "Slide 1.png", inline=False)
    assert "response-content-disposition=attachment" in download

    with Stubber(storage.client) as stub:
        stub.add_response(
            "head_object",
            {"ContentLength": 42, "ContentType": "image/png"},
            {"Bucket": "cp-creatives", "Key": "orgs/1/a.png"},
        )
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
        info = await storage.head("orgs/1/a.png")
        assert (info.size, info.content_type) == (42, "image/png")
        assert await storage.head("orgs/1/missing.png") is None


# --- The whole journey goes through the LLM gateway ---------------------------------


async def test_every_model_call_in_the_journey_goes_through_the_gateway(
    client, internet, design_ai, db
):
    """Discovery -> trend analysis -> topic -> strategy draft -> post -> design
    brief: every model call is rate limited and recorded by the gateway."""
    admin, org = await setup_org(client)
    await in_design(admin, org)
    topic = await gpt6_topic(admin)
    suggestion = await admin.post(
        f"/api/v1/topics/{topic['id']}/strategies/suggest", json={"platform": "linkedin"}
    )
    assert suggestion.json()["source"] == "ai"

    rows = list(await db.scalars(select(LLMRequest)))
    # One row per model request: nothing reached the model without the gateway.
    assert len(rows) == len(design_ai.calls) > 0
    assert {r.workflow for r in rows} == {
        "trend_alignment",
        "content_strategy",
        "post_generation",
        "design_brief",
    }
    assert all(r.status == "succeeded" and r.input_tokens for r in rows)
    jobs = list(
        await db.scalars(select(AIGenerationJob).where(AIGenerationJob.provider != "rules"))
    )
    recorded = {r.job_id for r in rows}
    assert jobs and all(j.id in recorded for j in jobs if j.status.value == "succeeded")


# --- AI images ----------------------------------------------------------------------


class FakeImages:
    name, model = "fakeimg", "img-1"

    def __init__(self, fail: AIError | None = None) -> None:
        self.prompts: list[tuple[str, str]] = []
        self.fail = fail

    async def generate(self, prompt: str, ratio: str):
        from app.ai.images import GeneratedImage

        self.prompts.append((prompt, ratio))
        if self.fail:
            raise self.fail
        return GeneratedImage(data=PNG, mime_type="image/png", provider=self.name, model=self.model)


@pytest.fixture
def fake_images():
    from app.ai.images import set_image_provider

    images = FakeImages()
    set_image_provider(images)
    yield images
    set_image_provider(None)


async def test_ai_image_becomes_the_next_design_version(
    client, internet, design_ai, fake_images, db
):
    admin, org = await setup_org(client)
    post, task = await in_design(admin, org)
    assert task["ai_images"] is True and task["image_job"] is None
    url = f"{API}/{task['id']}"

    resp = await admin.post(f"{url}/generate-image")
    assert resp.status_code == 202
    await runner.wait_idle()
    task = (await admin.get(url)).json()
    assert task["image_job"]["status"] == "succeeded" and task["image_job"]["version"] == 1
    [version] = task["creatives"]
    assert version["note"].startswith("Generated with AI")
    assert version["files"][0]["file_type"] == "image/png"
    prompt, ratio = fake_images.prompts[0]
    assert task["headline"] in prompt and ratio == "4:5"  # LinkedIn carousel 1080×1350
    # It's an ordinary version: review it, then submit it for approval.
    assert (await admin.get(f"/api/v1/content/{post['id']}")).json()["status"] == "design_uploaded"
    assert (await admin.post(f"{url}/submit")).status_code == 200

    rows = list(await db.scalars(select(LLMRequest).where(LLMRequest.workflow == "design_image")))
    assert [r.status for r in rows] == ["succeeded"]


async def test_ai_image_failures_are_explained(client, internet, design_ai, fake_images):
    from app.ai.images import NOT_IN_PLAN

    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    fake_images.fail = AIError(AIErrorKind.QUOTA_EXHAUSTED, NOT_IN_PLAN, public=True)
    await admin.post(f"{API}/{task['id']}/generate-image")
    await runner.wait_idle()
    task = (await admin.get(f"{API}/{task['id']}")).json()
    assert task["image_job"]["status"] == "failed" and "billing" in task["image_job"]["error"]
    assert task["creatives"] == []

    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.post(f"{API}/{task['id']}/generate-image")).status_code == 403


async def test_gemini_free_tier_without_images_is_explained():
    import httpx

    from app.ai.images import GeminiImages, aspect_ratio

    body = {"error": {"code": 429, "message": "Quota exceeded for metric: x, limit: 0, model: y"}}
    images = GeminiImages(
        model="gemini-2.5-flash-image",
        api_key="k",
        timeout=5,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(429, json=body))
        ),
    )
    with pytest.raises(AIError) as exc:
        await images.generate("a cat", "1:1")
    assert exc.value.kind == AIErrorKind.QUOTA_EXHAUSTED and "billing" in exc.value.user_message
    assert not exc.value.retryable
    assert aspect_ratio("1200×630 (1.91:1)") == "16:9"
    assert aspect_ratio("1080×1920") == "9:16" and aspect_ratio(None) == "1:1"


async def test_cloudflare_images_request_and_responses():
    import base64
    import json as _json

    import httpx

    from app.ai.images import CloudflareImages

    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    seen: list[dict] = []

    def reply_json(request: httpx.Request) -> httpx.Response:
        seen.append(_json.loads(request.content))
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"result": {"image": base64.b64encode(jpeg).decode()}})

    def adapter(handler, model="@cf/leonardo/lucid-origin"):
        return CloudflareImages(
            model=model,
            account_id="acc",
            api_token="tok",
            timeout=5,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    image = await adapter(reply_json).generate("a cat", "16:9")
    assert image.mime_type == "image/jpeg" and image.data == jpeg
    assert (seen[0]["width"], seen[0]["height"]) == (1280, 720)
    await adapter(reply_json, "@cf/black-forest-labs/flux-1-schnell").generate("a cat", "16:9")
    assert "width" not in seen[1]  # fixed-size model

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    raw = adapter(lambda r: httpx.Response(200, content=png, headers={"content-type": "image/png"}))
    assert (await raw.generate("a cat", "1:1")).mime_type == "image/png"

    daily = {
        "errors": [{"message": "you have used up your daily free allocation of 10,000 neurons"}]
    }
    with pytest.raises(AIError) as exc:
        await adapter(lambda r: httpx.Response(429, json=daily)).generate("a cat", "1:1")
    assert exc.value.kind == AIErrorKind.QUOTA_EXHAUSTED and "tomorrow" in exc.value.user_message
    with pytest.raises(AIError) as exc:
        await adapter(lambda r: httpx.Response(401, json={"errors": []})).generate("a cat", "1:1")
    assert exc.value.kind == AIErrorKind.AUTH


def test_cloudflare_is_picked_automatically():
    from app.ai.images import get_image_provider
    from app.core.config import Settings

    settings = Settings(_env_file=None, cloudflare_account_id="acc", cloudflare_api_key="tok")
    provider = get_image_provider(settings)
    assert (provider.name, provider.model) == ("cloudflare", "@cf/black-forest-labs/flux-1-schnell")
    assert get_image_provider(Settings(_env_file=None, cloudflare_account_id="acc")) is None


async def test_kie_images_create_poll_and_download():
    import json as _json

    import httpx

    from app.ai.images import KieImages

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    states = iter(["waiting", "generating", "success"])
    created: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/createTask"):
            created.append(_json.loads(request.content))
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "t1"}})
        if request.url.path.endswith("/recordInfo"):
            assert request.url.params["taskId"] == "t1"
            state = next(states)
            result = _json.dumps({"resultUrls": ["https://files.example.com/a.png"]})
            return httpx.Response(
                200, json={"code": 200, "data": {"state": state, "resultJson": result}}
            )
        return httpx.Response(200, content=png)

    def kie(handler):
        images = KieImages(
            model="seedream/5-flash-text-to-image",
            api_key="k",
            timeout=60,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        async def no_wait(_):
            return None

        images.sleep = no_wait
        return images

    image = await kie(handler).generate("a cat", "4:5")
    assert image.data == png and image.mime_type == "image/png"
    assert created[0]["model"] == "seedream/5-flash-text-to-image"
    assert created[0]["input"]["aspect_ratio"] == "3:4"  # nearest ratio Seedream accepts

    no_credits = lambda r: httpx.Response(200, json={"code": 402, "msg": "insufficient credits"})  # noqa: E731
    with pytest.raises(AIError) as exc:
        await kie(no_credits).generate("a cat", "1:1")
    assert exc.value.kind == AIErrorKind.QUOTA_EXHAUSTED and "credits" in exc.value.user_message

    def failed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/createTask"):
            return httpx.Response(200, json={"code": 200, "data": {"taskId": "t2"}})
        return httpx.Response(200, json={"code": 200, "data": {"state": "fail", "failMsg": "boom"}})

    with pytest.raises(AIError) as exc:
        await kie(failed).generate("a cat", "1:1")
    assert exc.value.kind == AIErrorKind.BAD_OUTPUT and not exc.value.retryable


def test_kie_is_preferred_when_its_key_is_set():
    from app.ai.images import get_image_provider
    from app.core.config import Settings

    settings = Settings(
        _env_file=None, kie_ai_api_key="k", cloudflare_account_id="a", cloudflare_api_key="t"
    )
    assert get_image_provider(settings).name == "kie"
    explicit = Settings(_env_file=None, kie_ai_api_key="k", image_provider="cloudflare")
    assert get_image_provider(explicit) is None  # Cloudflare chosen but not set up


async def test_daily_image_cap_is_explained(
    client, internet, design_ai, fake_images, monkeypatch
):
    from app.ai.limits import quota_limiter
    from app.core.config import get_settings

    settings = get_settings().model_copy(update={"llm_limits": {"fakeimg/*": {"rpd": 1}}})
    quota_limiter.configure(settings)
    try:
        admin, org = await setup_org(client)
        _, task = await in_design(admin, org)
        url = f"{API}/{task['id']}"
        await admin.post(f"{url}/generate-image")
        await runner.wait_idle()
        assert (await admin.get(url)).json()["image_job"]["status"] == "succeeded"

        await admin.post(f"{url}/generate-image")
        await runner.wait_idle()
        job = (await admin.get(url)).json()["image_job"]
        assert job["status"] == "failed"
        assert "allowance is used up" in job["error"]
        assert len(fake_images.prompts) == 1  # the provider was never called
    finally:
        quota_limiter.configure(get_settings())


def test_broken_s3_client_falls_back_to_local_storage(monkeypatch):
    from botocore.exceptions import MissingDependencyException

    import app.storage as storage_module
    from app.core.config import get_settings
    from app.storage import s3

    def broken(*args, **kwargs):
        raise MissingDependencyException(msg="needs botocore[crt]")

    settings = get_settings()
    monkeypatch.setattr(settings, "s3_bucket", "some-bucket")
    monkeypatch.setattr(s3.boto3, "client", broken)
    storage_module._storage.cache_clear()
    storage_module._s3_ready.cache_clear()
    try:
        assert storage_module.storage_provider() == "local"
        assert storage_module.get_storage().name == "local"
    finally:
        storage_module._storage.cache_clear()
        storage_module._s3_ready.cache_clear()
