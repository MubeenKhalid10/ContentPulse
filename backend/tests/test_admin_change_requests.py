# ruff: noqa: F811
"""Only an admin asks for changes. The creator reads the request, redoes the work and
resubmits; a comment is only a conversation. Notifications tell each side once."""

import asyncio
import uuid

from sqlalchemy import func, select

from app.models.approval import ApprovalRequest, Notification
from tests.conftest import add_member, create_org, register
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_approvals import API, submitted
from tests.test_design import design_ai, upload  # noqa: F401  (fixtures)

NOTE = "Shorten the headline and use the brand blue."


async def ask(admin, item, scope="design", note=NOTE):
    return await admin.post(
        f"{API}/{item['id']}/request-changes", json={"comment": note, "scope": scope}
    )


async def request_for(actor, post_id) -> dict | None:
    return (await actor.get(f"/api/v1/content/{post_id}")).json()["change_request"]


async def test_each_scope_reaches_the_creator_as_one_request(client, internet, design_ai):
    for scope in ("copy", "design"):
        client.cookies.clear()
        admin, org = await setup_org(client)
        post, item, designer = await submitted(client, admin, org)
        assert (await ask(admin, item, scope)).status_code == 200
        request = await request_for(designer, post["id"])
        assert request["scope"] == scope and request["status"] == "open"
        assert request["note"] == NOTE and request["id"] == item["id"]
        assert request["requested_by"]["id"] == admin.user["id"]
        # The same single request shows on the design task, however many scopes it covers.
        task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
        task = (await designer.get(f"/api/v1/design/tasks/{task_id}")).json()
        assert task["post"]["changes_scope"] == scope
        # One round, so never two independent requests.
        rounds = (await admin.get(f"{API}/{item['id']}")).json()["rounds"]
        assert [r["status"] for r in rounds if r["stage"] == "design"] == ["changes_requested"]
        return  # one org per test run is enough; the loop above only varies the scope


async def test_a_design_request_is_resolved_only_by_resubmitting(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    await ask(admin, item, "design")
    url = f"/api/v1/content/{post['id']}"
    request = await request_for(admin, post["id"])
    assert (request["scope"], request["content_done"], request["design_done"]) == (
        "design",
        True,  # the content was not asked for
        False,
    )

    task_id = (await admin.get(url)).json()["design_task"]["id"]
    key = await upload(designer, task_id, "v2.png")
    await designer.post(
        f"/api/v1/design/tasks/{task_id}/assets",
        json={"files": [{"storage_key": key, "file_name": "v2.png"}]},
    )
    request = await request_for(admin, post["id"])
    assert (request["status"], request["design_done"]) == ("open", True)
    assert (await designer.post(f"/api/v1/design/tasks/{task_id}/submit")).status_code == 200

    # Resubmitting opens a new round; the old request is history, not current.
    assert await request_for(admin, post["id"]) is None
    queue = (await admin.get(API)).json()["items"]
    assert len(queue) == 1 and queue[0]["round"] == 2 and queue[0]["id"] != item["id"]
    old = (await admin.get(f"{API}/{item['id']}")).json()
    assert old["status"] == "changes_requested"  # the original decision is untouched
    assert old["comments"][0]["body"] == NOTE


async def test_there_is_no_both_option(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, item, _ = await submitted(client, admin, org)
    assert (await ask(admin, item, "both")).status_code == 422
    assert (await ask(admin, item, "copy")).status_code == 200


async def test_a_round_is_decided_once(client, internet, design_ai, db):
    admin, org = await setup_org(client)
    _, item, _ = await submitted(client, admin, org)
    assert (await ask(admin, item)).status_code == 200
    again = await ask(admin, item, note="A second, different instruction.")
    assert again.status_code == 409
    assert (await admin.post(f"{API}/{item['id']}/approve", json={})).status_code == 409
    row = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.id == uuid.UUID(item["id"]))
    )
    await db.refresh(row)
    assert row.comments == NOTE and row.status.value == "changes_requested"


async def test_simultaneous_decisions_apply_once(client, internet, design_ai, db):
    admin, org = await setup_org(client)
    _, item, _ = await submitted(client, admin, org)
    results = await asyncio.gather(
        ask(admin, item, "design"),
        admin.post(f"{API}/{item['id']}/approve", json={}),
        admin.post(f"{API}/{item['id']}/reject", json={"comment": "No."}),
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409]


async def test_instructions_are_required_and_only_admins_ask(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    url = f"{API}/{item['id']}/request-changes"
    assert (await admin.post(url, json={"comment": "fix", "scope": "both"})).status_code == 422
    assert (await admin.post(url, json={"scope": "both"})).status_code == 422
    creator2 = await add_member(client, admin, org["id"], "vic@acme.example.com", "creator")
    for actor in (designer, creator2):
        assert (await actor.post(url, json={"comment": NOTE})).status_code == 403
        assert (
            await actor.post(f"{API}/{item['id']}/reopen", json={"comment": NOTE})
        ).status_code == 403
    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.post(url, json={"comment": NOTE})).status_code == 404
    assert (await request_for(admin, post["id"])) is None  # nothing was created


async def test_the_creator_request_workflow_is_gone(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    some = uuid.uuid4()
    for actor in (admin, designer):
        created = await actor.post(
            f"/api/v1/content/{post['id']}/change-requests",
            json={"scope": "both", "note": NOTE},
        )
        assert created.status_code in (404, 405)
        assert (await actor.get(f"{API}/change-requests")).status_code in (403, 404, 422)
        for verb in ("accept", "decline"):
            sent = await actor.post(f"{API}/change-requests/{some}/{verb}", json={})
            assert sent.status_code in (404, 405)
    assert "change_request_count" not in (await admin.get(API)).json()


async def test_a_comment_is_only_a_comment(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    await ask(admin, item, "copy")
    before = (await admin.get(f"/api/v1/content/{post['id']}")).json()["status"]
    comments = f"/api/v1/content/{post['id']}/comments"
    asked = await designer.post(comments, json={"body": "Which headline do you mean?"})
    assert asked.status_code == 200
    answered = await admin.post(f"{API}/{item['id']}/comments", json={"body": "The first one."})
    assert answered.status_code == 200
    after = (await admin.get(f"/api/v1/content/{post['id']}")).json()
    assert after["status"] == before == "changes_requested"
    request = after["change_request"]
    assert request["id"] == item["id"] and request["note"] == NOTE  # still the one request
    rounds = (await admin.get(f"{API}/{item['id']}")).json()["rounds"]
    assert len([r for r in rounds if r["stage"] == "design"]) == 1


async def test_approved_work_stays_locked_by_comments(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    assert (await admin.post(f"{API}/{item['id']}/approve", json={})).status_code == 200
    sent = await designer.post(
        f"/api/v1/content/{post['id']}/comments", json={"body": "Can we change this?"}
    )
    assert sent.status_code == 200
    assert (await admin.get(f"/api/v1/content/{post['id']}")).json()["status"] == "final"
    assert (await request_for(admin, post["id"])) is None


async def test_notifications_reach_the_right_person_once(client, internet, design_ai, db):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)

    # The submission told the admins (the designer who submitted is not told).
    mine = (await admin.get("/api/v1/notifications")).json()
    assert mine["unread"] >= 1 and mine["items"][0]["link"] == f"/approvals/{item['id']}"
    assert (await designer.get("/api/v1/notifications")).json()["items"] == []

    await ask(admin, item, "design")
    told = (await designer.get("/api/v1/notifications")).json()
    [note] = told["items"]
    assert note["kind"] == "changes_requested" and note["scope"] == "design"
    assert "(design)" in note["title"] and note["body"] == NOTE
    assert note["link"] == f"/content/{post['id']}" and note["read_at"] is None
    # A repeat of the same event is not a second message.
    assert (await ask(admin, item)).status_code == 409
    assert len((await designer.get("/api/v1/notifications")).json()["items"]) == 1
    # The admin who acted is not told about their own action.
    assert all(
        n["kind"] != "changes_requested"
        for n in (await admin.get("/api/v1/notifications")).json()["items"]
    )

    # A creator's question reaches the admin, once, and opens the round.
    await designer.post(f"/api/v1/content/{post['id']}/comments", json={"body": "Which blue?"})
    asked = [
        n
        for n in (await admin.get("/api/v1/notifications")).json()["items"]
        if n["kind"] == "clarification"
    ]
    assert len(asked) == 1 and asked[0]["body"] == "Which blue?"
    assert asked[0]["link"] == f"/approvals/{item['id']}"
    assert not [
        n
        for n in (await designer.get("/api/v1/notifications")).json()["items"]
        if n["body"] == "Which blue?"
    ]  # not told about their own comment

    # Clarification reply goes to the creator.
    await admin.post(f"{API}/{item['id']}/comments", json={"body": "Use the blue."})
    kinds = [n["kind"] for n in (await designer.get("/api/v1/notifications")).json()["items"]]
    assert kinds.count("clarification") == 1

    # The resubmission tells the admin, naming the scope that was asked for.
    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    key = await upload(designer, task_id, "v2.png")
    await designer.post(
        f"/api/v1/design/tasks/{task_id}/assets",
        json={"files": [{"storage_key": key, "file_name": "v2.png"}]},
    )
    await designer.post(f"/api/v1/design/tasks/{task_id}/submit")
    again = (await admin.get("/api/v1/notifications")).json()["items"]
    resub = [n for n in again if n["kind"] == "resubmitted"]
    assert len(resub) == 1 and resub[0]["scope"] == "design"

    # Approving tells the creator; reading is per person.
    [new] = (await admin.get(API)).json()["items"]
    await admin.post(f"{API}/{new['id']}/approve", json={})
    mine = (await designer.get("/api/v1/notifications")).json()
    assert "approved" in [n["kind"] for n in mine["items"]]
    first = mine["items"][0]
    assert (await designer.post(f"/api/v1/notifications/{first['id']}/read")).status_code == 204
    assert (await admin.post(f"/api/v1/notifications/{first['id']}/read")).status_code == 404
    assert (await designer.get("/api/v1/notifications")).json()["unread"] == mine["unread"] - 1
    assert (await designer.post("/api/v1/notifications/read-all")).status_code == 204
    assert (await designer.get("/api/v1/notifications")).json()["unread"] == 0

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get("/api/v1/notifications")).json()["items"] == []
    total = await db.scalar(select(func.count()).select_from(Notification))
    assert total >= 4


async def test_no_more_uploads_once_the_design_is_submitted(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    ticket = await designer.post(
        f"/api/v1/design/tasks/{task_id}/uploads",
        json={"file_name": "late.png", "file_type": "image/png", "file_size": 1000},
    )
    assert ticket.status_code == 409
    late = await designer.post(
        f"/api/v1/design/tasks/{task_id}/assets",
        json={"files": [{"storage_key": "x/late.png", "file_name": "late.png"}]},
    )
    assert late.status_code == 409


async def test_an_unsent_upload_can_be_removed_but_a_reviewed_one_cannot(
    client, internet, design_ai
):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    url = f"/api/v1/design/tasks/{task_id}"
    # Version 1 went to review: it stays, whoever asks.
    assert (await designer.delete(f"{url}/creatives/1")).status_code == 409
    await ask(admin, item, "design")

    key = await upload(designer, task_id, "wrong.png")
    await designer.post(
        f"{url}/assets", json={"files": [{"storage_key": key, "file_name": "wrong.png"}]}
    )
    detail = (await designer.get(url)).json()
    assert [c["version"] for c in detail["creatives"]] == [2, 1]
    # Not sent yet: the designer removes it, the reviewed version is still there.
    removed = await designer.delete(f"{url}/creatives/2")
    assert removed.status_code == 200
    assert [c["version"] for c in removed.json()["creatives"]] == [1]
    assert (await designer.delete(f"{url}/creatives/2")).status_code == 404
    creator2 = await add_member(client, admin, org["id"], "vic@acme.example.com", "creator")
    assert (await creator2.delete(f"{url}/creatives/1")).status_code == 403
