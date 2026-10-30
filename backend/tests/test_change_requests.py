"""A creator asks an admin to reopen locked work; the admin decides. Approvals
themselves are for admins: everyone else follows a post from the post."""

from tests.conftest import add_member
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_approvals import submitted
from tests.test_content import approved_strategy, content_ai, generated  # noqa: F401  (fixtures)
from tests.test_design import design_ai  # noqa: F401  (fixtures)

APPROVALS = "/api/v1/approvals"
QUEUE = f"{APPROVALS}/change-requests"
CONTENT = "/api/v1/content"


async def ask(user, post_id, scope, note="Please change the headline."):
    return await user.post(
        f"{CONTENT}/{post_id}/change-requests", json={"scope": scope, "note": note}
    )


async def detail(user, post_id) -> dict:
    return (await user.get(f"{CONTENT}/{post_id}")).json()


async def test_creator_asks_during_design_approval_and_admin_accepts(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    assert (await detail(creator, post["id"]))["change_request_scopes"] == [
        "copy",
        "design",
        "both",
    ]

    resp = await ask(creator, post["id"], "design", "Slide 3 has a typo.")
    assert resp.status_code == 201, resp.text
    request = resp.json()
    assert request["status"] == "pending" and request["requested_by"]["id"] == creator.user["id"]

    # Asking changes nothing yet: the work stays locked and the tag shows on the post.
    seen = await detail(creator, post["id"])
    assert seen["status"] == "pending_approval"
    assert seen["change_request"]["scope"] == "design"
    assert (await creator.post(f"{QUEUE}/{request['id']}/accept")).status_code == 403
    page = (await admin.get(QUEUE)).json()
    assert page["total"] == 1 and page["items"][0]["post"]["id"] == post["id"]
    assert (await admin.get(APPROVALS)).json()["change_request_count"] == 1

    accepted = await admin.post(f"{QUEUE}/{request['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decided_by"]["id"] == admin.user["id"]

    seen = await detail(creator, post["id"])
    assert seen["status"] == "changes_requested" and seen["changes_scope"] == "design"
    assert seen["change_request"] is None  # the post's status tells the story now
    assert "Slide 3 has a typo." in seen["review"]["comments"][0]["body"]
    assert (await admin.get(QUEUE)).json()["total"] == 0


async def test_creator_asks_after_final_approval_and_both_reopen(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    await admin.post(f"{APPROVALS}/{item['id']}/approve", json={})
    assert (await detail(creator, post["id"]))["status"] == "final"

    request = (await ask(creator, post["id"], "both")).json()
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 200
    seen = await detail(creator, post["id"])
    assert seen["status"] == "changes_requested" and seen["changes_scope"] == "both"
    assert seen["editable"] is True


async def test_declined_request_stays_visible_and_keeps_the_lock(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    await admin.post(f"{APPROVALS}/{item['id']}/approve", json={})
    request = (await ask(creator, post["id"], "copy")).json()

    resp = await admin.post(f"{QUEUE}/{request['id']}/decline", json={"comment": "Already live."})
    assert resp.status_code == 200, resp.text
    seen = await detail(creator, post["id"])
    assert seen["status"] == "final"
    assert seen["change_request"]["status"] == "declined"
    assert seen["change_request"]["decision_note"] == "Already live."
    # A decided request can't be decided again, and they may ask again.
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 409
    assert (await ask(creator, post["id"], "design")).status_code == 201


async def test_during_content_approval_only_the_copy_can_be_asked_for(
    client, internet, content_ai
):
    admin, org = await setup_org(client)
    post = await generated(admin, await approved_strategy(admin, org))
    creator = await add_member(client, admin, org["id"], "cam@acme.example.com", "creator")
    # Nothing is locked in a draft: they can simply edit it.
    assert (await detail(creator, post["id"]))["change_request_scopes"] == []
    assert (await ask(creator, post["id"], "copy")).status_code == 409

    await admin.post(f"{CONTENT}/{post['id']}/submit-for-review")
    assert (await detail(creator, post["id"]))["change_request_scopes"] == ["copy"]
    assert (await ask(creator, post["id"], "design")).status_code == 409
    request = (await ask(creator, post["id"], "copy")).json()
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 200
    seen = await detail(creator, post["id"])
    assert seen["status"] == "draft" and seen["changes_scope"] == "copy"


async def test_after_content_approval_the_copy_can_be_reopened(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    # Take the design back: the copy is approved and the design is open again.
    task = (await detail(admin, post["id"]))["design_task"]
    await creator.post(f"/api/v1/design/tasks/{task['id']}/withdraw")
    assert (await detail(creator, post["id"]))["change_request_scopes"] == ["copy"]
    request = (await ask(creator, post["id"], "copy")).json()
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 200
    assert (await detail(creator, post["id"]))["status"] == "draft"


async def test_only_one_request_waits_and_viewers_cant_ask(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await ask(viewer, post["id"], "copy")).status_code == 403
    assert (await ask(creator, post["id"], "copy")).status_code == 201
    assert (await ask(creator, post["id"], "design")).status_code == 409


async def test_the_admins_own_decision_closes_an_open_request(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    request = (await ask(creator, post["id"], "design")).json()

    await admin.post(
        f"{APPROVALS}/{item['id']}/request-changes", json={"comment": "New logo.", "scope": "both"}
    )
    assert (await admin.get(QUEUE)).json()["total"] == 0
    assert (await detail(creator, post["id"]))["change_request"] is None
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 409


async def test_approval_still_leaves_a_waiting_request_open(client, internet, design_ai):
    admin, org = await setup_org(client)
    post, item, creator = await submitted(client, admin, org)
    request = (await ask(creator, post["id"], "design")).json()
    await admin.post(f"{APPROVALS}/{item['id']}/approve", json={})
    assert (await detail(creator, post["id"]))["change_request"]["status"] == "pending"
    # Accepting now reopens the approved post instead of deciding a waiting round.
    assert (await admin.post(f"{QUEUE}/{request['id']}/accept")).status_code == 200
    assert (await detail(creator, post["id"]))["status"] == "changes_requested"


async def test_approvals_are_for_admins_only(client, internet, design_ai):
    admin, org = await setup_org(client)
    _, item, creator = await submitted(client, admin, org)
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    for user in (creator, viewer):
        assert (await user.get(APPROVALS)).status_code == 403
        assert (await user.get(f"{APPROVALS}/{item['id']}")).status_code == 403
        assert (await user.get(QUEUE)).status_code == 403
    assert "approval.read" not in (await creator.get("/api/v1/auth/me")).json()["permissions"]
    assert "approval.read" not in (await viewer.get("/api/v1/auth/me")).json()["permissions"]
    assert "approval.read" in (await admin.get("/api/v1/auth/me")).json()["permissions"]
