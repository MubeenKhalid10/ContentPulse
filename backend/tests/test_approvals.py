"""Sprint 8: approval queue, review, comments pinned to versions, request
changes → revision → re-submit, reject, final (spec §31-33, §42, §53)."""

import uuid

from tests.conftest import add_member, create_org, register
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_design import design_ai, in_design, upload  # noqa: F401  (fixtures)

API = "/api/v1/approvals"


async def submitted(client, admin, org) -> tuple[dict, dict, object]:
    """Post designed by a designer and submitted; returns (post, approval, designer)."""
    post, task = await in_design(admin, org)
    designer = await add_member(client, admin, org["id"], "dee@acme.example.com", "creator")
    key = await upload(designer, task["id"])
    await designer.post(
        f"/api/v1/design/tasks/{task['id']}/assets",
        json={"files": [{"storage_key": key, "file_name": "slide-1.png"}]},
    )
    resp = await designer.post(f"/api/v1/design/tasks/{task['id']}/submit")
    assert resp.status_code == 200, resp.text
    queue = (await admin.get(API)).json()
    assert queue["total"] == 1
    return post, queue["items"][0], designer


async def test_submission_enters_the_queue_with_full_context(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)

    assert item["status"] == "pending" and item["round"] == 1
    assert (item["post_version"], item["creative_version"]) == (1, 1)
    assert item["post"]["status"] == "pending_approval"
    assert item["submitted_by"]["id"] == designer.user["id"] and item["reviewer"] is None
    assert item["preview_url"].startswith("/api/v1/storage/local/")
    assert item["topic_title"].lower().startswith("gpt-6")

    detail = (await admin.get(f"{API}/{item['id']}")).json()
    assert detail["content"]["hook"] == post["current"]["hook"] and not detail["copy_changed_since"]
    assert (
        detail["creative"]["version"] == 1
        and detail["creative"]["files"][0]["file_name"] == "slide-1.png"
    )
    assert detail["brief"]["format"] == "carousel"
    topic = detail["topic"]
    assert topic["relevance_level"] == "highly_relevant" and topic["sources"]  # trend sources (§53)
    assert topic["coverage"] and topic["coverage"][0]["url"]
    assert [v["version_number"] for v in detail["versions"]] == [1]
    assert [r["status"] for r in detail["rounds"]] == ["pending"] and detail["comments"] == []

    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["pending_approval"] == 1
    # Creators see the queue (to follow their posts) but can't decide.
    assert (await designer.get(API)).status_code == 200
    assert (await designer.post(f"{API}/{item['id']}/approve", json={})).status_code == 403


async def test_approve_then_final(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    url = f"{API}/{item['id']}"

    assert (await manager.post(f"{url}/approve", json={})).status_code == 403  # admins review
    approved = (await admin.post(f"{url}/approve", json={"comment": "Great work."})).json()
    assert approved["status"] == "approved" and approved["reviewer"]["id"] == admin.user["id"]
    # One click: approving makes the post final (locked, ready to publish).
    assert approved["post"]["status"] == "final" and approved["reviewed_at"]
    [comment] = approved["comments"]
    assert (comment["kind"], comment["post_version"], comment["creative_version"]) == (
        "approved",
        1,
        1,
    )

    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    assert (await admin.get(f"/api/v1/design/tasks/{task_id}")).json()["status"] == "completed"
    again = await admin.post(f"{url}/reject", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    assert (await admin.post(f"{url}/finalize")).status_code == 409  # already final
    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["approved"] == 1 and summary["pending_approval"] == 0
    assert (await admin.get(API, params={"status": "approved"})).json()["total"] == 1


async def test_changes_requested_revision_and_resubmit(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, designer = await submitted(client, admin, org)
    url = f"{API}/{item['id']}"

    missing = await admin.post(f"{url}/request-changes", json={})
    assert missing.status_code == 422  # a reason is required
    changed = (
        await admin.post(f"{url}/request-changes", json={"comment": "Reduce the text on slide 3."})
    ).json()
    assert (
        changed["status"] == "changes_requested"
        and changed["post"]["status"] == "changes_requested"
    )
    assert changed["comments"][0]["kind"] == "changes_requested"
    assert changed["comments"][0]["creative_version"] == 1  # pinned to what was reviewed (§33)

    # Back on the designer's list, with the feedback attached.
    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    task = (await designer.get(f"/api/v1/design/tasks/{task_id}")).json()
    assert task["status"] == "in_progress" and task["assignee"]["id"] == designer.user["id"]
    assert task["review"]["status"] == "changes_requested"
    assert task["review"]["comments"][0]["body"] == "Reduce the text on slide 3."
    studio = (await admin.get(f"/api/v1/content/{post['id']}")).json()
    assert studio["review"]["status"] == "changes_requested" and studio["editable"] is True

    key = await upload(designer, task_id, "slide-1-v2.png")
    uploaded = (
        await designer.post(
            f"/api/v1/design/tasks/{task_id}/assets",
            json={"files": [{"storage_key": key, "file_name": "slide-1-v2.png"}]},
        )
    ).json()
    assert (
        uploaded["post"]["status"] == "design_uploaded" and uploaded["creatives"][0]["version"] == 2
    )
    resubmitted = await designer.post(
        f"/api/v1/design/tasks/{task_id}/submit", json={"note": "Cut slide 3 to one line."}
    )
    assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "submitted"

    queue = (await admin.get(API)).json()
    [round2] = queue["items"]
    assert round2["round"] == 2 and round2["creative_version"] == 2 and round2["id"] != item["id"]
    detail = (await admin.get(f"{API}/{round2['id']}")).json()
    assert [r["status"] for r in detail["rounds"]] == ["changes_requested", "pending"]
    assert [c["kind"] for c in detail["comments"]] == ["changes_requested", "resubmitted"]
    assert detail["comments"][1]["creative_version"] == 2
    assert [c["version"] for c in detail["creatives"]] == [2, 1]  # nothing replaced
    assert (await admin.get(API, params={"status": "reviewed"})).json()["total"] == 1


async def test_copy_only_changes_resubmit_from_the_studio(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, _ = await submitted(client, admin, org)
    await admin.post(
        f"{API}/{item['id']}/request-changes",
        json={"comment": "Stronger headline.", "scope": "copy"},
    )
    task_id = (await admin.get(f"/api/v1/content/{post['id']}")).json()["design_task"]["id"]
    # The designer isn't asked to redo anything.
    assert (await admin.get(f"/api/v1/design/tasks/{task_id}")).json()["status"] == "submitted"

    url = f"/api/v1/content/{post['id']}"
    edited = await admin.patch(url, json={"base_version": 1, "hook": "A stronger headline."})
    assert edited.status_code == 200 and edited.json()["current_version"] == 2
    resubmitted = await admin.post(f"{url}/resubmit", json={"note": "Headline rewritten."})
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "pending_approval"
    assert (
        resubmitted.json()["review"]["status"] == "pending"
        and resubmitted.json()["review"]["round"] == 2
    )

    queue = (await admin.get(API)).json()["items"]
    assert (queue[0]["post_version"], queue[0]["creative_version"]) == (2, 1)
    old = (await admin.get(f"{API}/{item['id']}")).json()
    assert old["copy_changed_since"] is True and old["content"]["version_number"] == 1
    assert (await admin.post(f"{url}/resubmit", json={})).status_code == 409  # already pending


async def test_reject(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, _ = await submitted(client, admin, org)
    rejected = (
        await admin.post(f"{API}/{item['id']}/reject", json={"comment": "Off-brand topic."})
    ).json()
    assert rejected["status"] == "rejected" and rejected["post"]["status"] == "rejected"
    studio = (await admin.get(f"/api/v1/content/{post['id']}")).json()
    assert studio["editable"] is False and studio["design_task"] is None  # task cancelled
    assert (await admin.post(f"/api/v1/content/{post['id']}/resubmit", json={})).status_code == 409
    assert (await admin.post(f"/api/v1/content/{post['id']}/archive")).json()[
        "status"
    ] == "archived"

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    assert {"APPROVAL_REQUESTED", "REJECTED"} <= {e["action"] for e in logs}


async def test_comments_and_permissions(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, item, designer = await submitted(client, admin, org)
    url = f"{API}/{item['id']}"
    manager = await add_member(client, admin, org["id"], "max@acme.example.com", "creator")
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")

    first = (await admin.post(f"{url}/comments", json={"body": "Love slide 1."})).json()
    assert first["comments"][0]["author"]["id"] == admin.user["id"]
    second = (await manager.post(f"{url}/comments", json={"body": "Agreed."})).json()
    assert [c["body"] for c in second["comments"]] == ["Love slide 1.", "Agreed."]
    assert all(c["post_version"] == 1 and c["creative_version"] == 1 for c in second["comments"])
    third = await designer.post(f"{url}/comments", json={"body": "Fixed slide 3."})
    assert third.status_code == 200  # creators can reply
    assert (await viewer.get(url)).status_code == 200  # read-only access
    assert (await viewer.post(f"{url}/comments", json={"body": "x"})).status_code == 403
    assert (await admin.post(f"{url}/comments", json={"body": "  "})).status_code == 422
    assert (await admin.get(API)).json()["items"][0]["comment_count"] == 3

    logs = (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    assert "APPROVAL_COMMENTED" in {e["action"] for e in logs}

    outsider = await register(client, "eve@other.example.com")
    await create_org(outsider, "Other Co")
    assert (await outsider.get(url)).status_code == 404
    assert (await outsider.post(f"{url}/approve", json={})).status_code == 404
    assert (await outsider.get(API)).json()["total"] == 0
    assert (await admin.get(f"{API}/{uuid.uuid4()}")).status_code == 404
