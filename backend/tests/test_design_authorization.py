"""Who may work on a design task, and the lock on copy and designs once they
are with an admin."""

import uuid

from sqlalchemy import select

from app.models.approval import ApprovalRequest
from app.models.design import DesignBrief
from app.models.enums import ApprovalStatus, DesignBriefStatus, PostStatus
from tests.conftest import add_member
from tests.test_approved_lock import API, edit, editable, make_post, setup

TASKS = "/api/v1/design/tasks"


async def make_task(
    db, org_id, post, assignee: uuid.UUID | None = None, status=DesignBriefStatus.OPEN
):
    brief = DesignBrief(
        organization_id=org_id,
        post_id=post.id,
        format="single_image",
        status=status,
        assignee_id=assignee,
    )
    db.add(brief)
    await db.commit()
    return brief


async def upload_ticket(actor, task_id):
    return await actor.post(
        f"{TASKS}/{task_id}/uploads",
        json={"file_name": "a.png", "file_type": "image/png", "file_size": 10},
    )


async def test_only_the_assignee_works_on_an_assigned_task(client, db):
    admin, creator, org_id = await setup(client, db)
    other = await add_member(client, admin, str(org_id), "other@acme.example.com", "creator")
    post = await make_post(db, org_id, PostStatus.DESIGN_PENDING)
    task = await make_task(db, org_id, post, assignee=uuid.UUID(creator.user["id"]))

    # Someone else on the team can't work on it ...
    assert (await upload_ticket(other, task.id)).status_code == 403
    assert (await other.post(f"{TASKS}/{task.id}/start")).status_code == 403
    # ... the assignee can, and so can an admin.
    assert (await upload_ticket(creator, task.id)).status_code == 200
    assert (await upload_ticket(admin, task.id)).status_code == 200


async def test_an_unassigned_task_can_be_taken_by_any_creator(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.DESIGN_PENDING)
    task = await make_task(db, org_id, post)

    assert (await upload_ticket(creator, task.id)).status_code == 200
    detail = (await creator.get(f"{TASKS}/{task.id}")).json()
    assert detail["assignee"]["id"] == creator.user["id"]


async def test_copy_is_locked_while_it_is_with_an_admin_and_the_writer_can_withdraw(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.CONTENT_REVIEW)

    assert not await editable(creator, post.id)
    resp = await creator.patch(f"{API}/{post.id}", json={"base_version": 1, "body": "x"})
    assert resp.status_code == 409 and "with an admin" in resp.json()["error"]["message"]

    # The writer asks for the change themselves by withdrawing it from review.
    resp = await creator.post(f"{API}/{post.id}/back-to-draft")
    assert resp.status_code == 200 and resp.json()["status"] == "draft"
    assert await editable(creator, post.id) and await edit(creator, post.id) == 200


async def test_the_designer_can_withdraw_a_submitted_design_before_an_admin_decides(client, db):
    admin, creator, org_id = await setup(client, db)
    other = await add_member(client, admin, str(org_id), "other@acme.example.com", "creator")
    post = await make_post(db, org_id, PostStatus.PENDING_APPROVAL, creative=True)
    task = await make_task(
        db, org_id, post, assignee=uuid.UUID(creator.user["id"]), status=DesignBriefStatus.SUBMITTED
    )
    db.add(
        ApprovalRequest(
            organization_id=org_id,
            post_id=post.id,
            post_version=1,
            creative_version=1,
            submitted_by=uuid.UUID(creator.user["id"]),
        )
    )
    await db.commit()

    assert (await other.post(f"{TASKS}/{task.id}/withdraw")).status_code == 403
    resp = await creator.post(f"{TASKS}/{task.id}/withdraw")
    assert resp.status_code == 200, resp.text
    assert resp.json()["post"]["status"] == "design_uploaded"
    post_id, task_id = (
        post.id,
        task.id,
    )  # read before expiring: expired rows can't lazy-load under asyncio
    db.expire_all()
    pending = await db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.post_id == post_id, ApprovalRequest.status == ApprovalStatus.PENDING
        )
    )
    assert list(pending) == []
    # Not waiting for approval any more: nothing left to withdraw.
    assert (await creator.post(f"{TASKS}/{task_id}/withdraw")).status_code == 409


async def test_a_design_with_files_can_be_submitted_even_if_the_post_was_never_moved_on(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.DESIGN_IN_PROGRESS, creative=True)
    task = await make_task(db, org_id, post, assignee=uuid.UUID(creator.user["id"]))

    resp = await creator.post(f"{TASKS}/{task.id}/submit")
    assert resp.status_code == 200, resp.text
    assert resp.json()["post"]["status"] == "pending_approval"
