"""Two requests at once, and background jobs that finish after the post moved
on: whoever comes second must be refused or ignored, never overwrite state.
Also the Celery task wrapper, which the in-process test backend never runs."""

import asyncio
import uuid

from sqlalchemy import func, select

from app.ai.images import set_image_provider
from app.ai.provider import set_ai_provider
from app.models.ai import AIGenerationJob
from app.models.approval import ApprovalRequest
from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import ApprovalStatus, DesignBriefStatus, JobStatus, PostStatus
from app.models.post import PostVersion
from app.workers.runner import runner
from tests.conftest import add_member
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_approved_lock import make_post, setup
from tests.test_content import ContentAI, approved_strategy, generated
from tests.test_design import DesignAI, FakeImages, in_design

CONTENT = "/api/v1/content"
APPROVALS = "/api/v1/approvals"
TASKS = "/api/v1/design/tasks"


async def design_review(client, db, status=PostStatus.PENDING_APPROVAL):
    """A post with a creative and a design task for the creator, in `status`."""
    admin, creator, org_id = await setup(client, db)
    other_admin = await add_member(client, admin, str(org_id), "second@acme.example.com", "admin")
    post = await make_post(db, org_id, status, creative=True)
    brief = DesignBrief(
        organization_id=org_id,
        post_id=post.id,
        format="post",
        assignee_id=uuid.UUID(creator.user["id"]),
        status=DesignBriefStatus.SUBMITTED
        if status == PostStatus.PENDING_APPROVAL
        else DesignBriefStatus.IN_PROGRESS,
    )
    db.add(brief)
    await db.commit()
    return admin, other_admin, creator, org_id, post.id, brief.id


# --- two requests at once ---------------------------------------------------------------


async def test_two_admins_approving_the_design_at_once_finish_the_post_once(client, db):
    admin, other_admin, _, org_id, post_id, brief_id = await design_review(client, db)
    request = ApprovalRequest(
        organization_id=org_id, post_id=post_id, post_version=1, creative_version=1
    )
    db.add(request)
    await db.commit()

    url = f"{APPROVALS}/{request.id}/approve"
    first, second = await asyncio.gather(admin.post(url, json={}), other_admin.post(url, json={}))
    assert sorted([first.status_code, second.status_code]) == [200, 409], (first.text, second.text)

    db.expire_all()
    assert (await db.get(DesignBrief, brief_id)).status == DesignBriefStatus.COMPLETED
    rounds = list(
        await db.scalars(select(ApprovalRequest).where(ApprovalRequest.post_id == post_id))
    )
    assert [r.status for r in rounds] == [ApprovalStatus.APPROVED]


async def test_an_approval_and_a_rejection_at_once_leave_one_decision(client, db):
    admin, other_admin, _, org_id, post_id, _ = await design_review(client, db)
    request = ApprovalRequest(
        organization_id=org_id, post_id=post_id, post_version=1, creative_version=1
    )
    db.add(request)
    await db.commit()

    request_id = request.id
    approve, reject = await asyncio.gather(
        admin.post(f"{APPROVALS}/{request.id}/approve", json={}),
        other_admin.post(f"{APPROVALS}/{request.id}/reject", json={"comment": "No."}),
    )
    assert sorted([approve.status_code, reject.status_code]) == [200, 409]
    db.expire_all()
    decided = await db.scalar(
        select(ApprovalRequest.status).where(ApprovalRequest.id == request_id)
    )
    won = ApprovalStatus.APPROVED if approve.status_code == 200 else ApprovalStatus.REJECTED
    assert decided == won  # the stored decision is the one that was accepted


async def test_a_double_click_on_submit_opens_one_approval_round(client, db):
    _, _, creator, org_id, post_id, brief_id = await design_review(
        client, db, PostStatus.DESIGN_UPLOADED
    )
    url = f"{TASKS}/{brief_id}/submit"
    first, second = await asyncio.gather(creator.post(url), creator.post(url))
    assert sorted([first.status_code, second.status_code]) == [200, 409], (first.text, second.text)

    db.expire_all()
    pending = await db.scalar(
        select(func.count())
        .select_from(ApprovalRequest)
        .where(ApprovalRequest.post_id == post_id, ApprovalRequest.status == ApprovalStatus.PENDING)
    )
    assert pending == 1


# --- a job that finishes after the post moved on ----------------------------------------


class BlockedImages(FakeImages):
    """Holds the image back until the test lets it through."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, prompt: str, ratio: str):
        self.started.set()
        await self.release.wait()
        return await super().generate(prompt, ratio)


async def test_an_image_that_arrives_after_the_post_was_archived_is_dropped(
    client,
    internet,
    db,
):
    images = BlockedImages()
    set_ai_provider(DesignAI())
    set_image_provider(images)
    try:
        admin, org = await setup_org(client)
        post, task = await in_design(admin, org)
        assert (await admin.post(f"{TASKS}/{task['id']}/generate-image")).status_code == 202
        await asyncio.wait_for(images.started.wait(), 10)

        # While the provider is still working, an admin archives the post.
        assert (await admin.post(f"{CONTENT}/{post['id']}/archive")).status_code == 200
        images.release.set()
        await runner.wait_idle()
    finally:
        set_image_provider(None)
        set_ai_provider(None)

    job = await db.scalar(select(AIGenerationJob).where(AIGenerationJob.type == "design_image"))
    assert job.status == JobStatus.FAILED and "waiting for a design" in job.error
    assert await db.scalar(select(func.count()).select_from(CreativeAsset)) == 0
    detail = (await admin.get(f"{CONTENT}/{post['id']}")).json()
    assert detail["status"] == "archived"


class BlockedAI(ContentAI):
    """Holds the post text back until the test lets it through."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False

    async def generate_structured(self, *, system, prompt, schema, max_tokens=16000):
        if self.block and "<strategy>" in prompt:
            self.started.set()
            await self.release.wait()
        return await super().generate_structured(
            system=system, prompt=prompt, schema=schema, max_tokens=max_tokens
        )


async def test_regenerated_text_that_arrives_after_the_post_was_archived_is_dropped(
    client,
    internet,
    db,
):
    ai = BlockedAI()
    set_ai_provider(ai)
    try:
        admin, org = await setup_org(client)
        post = await generated(admin, await approved_strategy(admin, org))
        assert post["current_version"] == 1
        ai.block = True
        resp = await admin.post(f"{CONTENT}/{post['id']}/regenerate", json={})
        assert resp.status_code == 202
        await asyncio.wait_for(ai.started.wait(), 10)

        assert (await admin.post(f"{CONTENT}/{post['id']}/archive")).status_code == 200
        ai.release.set()
        await runner.wait_idle()
    finally:
        set_ai_provider(None)

    versions = await db.scalar(
        select(func.count())
        .select_from(PostVersion)
        .where(PostVersion.post_id == uuid.UUID(post["id"]))
    )
    assert versions == 1  # the late text was not written
    job = await db.scalar(
        select(AIGenerationJob)
        .where(AIGenerationJob.entity_id == uuid.UUID(post["id"]))
        .order_by(AIGenerationJob.created_at.desc())
    )
    assert job.status == JobStatus.FAILED and "locked" in job.error
    assert (await admin.get(f"{CONTENT}/{post['id']}")).json()[
        "status"
    ] == PostStatus.ARCHIVED.value


# --- the Celery worker's task wrapper ---------------------------------------------------


def test_a_celery_worker_runs_the_named_job_with_the_entity_id(monkeypatch):
    """The worker receives the id as a string and runs the same async job the
    API runs in-process. (Registration and the in-process fallback are covered
    in test_operations.)"""
    from app.workers import celery_app as worker

    seen: list[uuid.UUID] = []

    async def job(entity_id: uuid.UUID) -> None:
        seen.append(entity_id)

    resolved: list[str] = []
    monkeypatch.setattr(worker, "resolve", lambda name: resolved.append(name) or job)
    entity = uuid.uuid4()
    worker.celery_app.tasks["contentpulse.design.image"].run(str(entity))
    assert (resolved, seen) == (["design.image"], [entity])
