"""Posts and design tasks an approver sent back get their own list."""

import uuid

from app.models.approval import ApprovalRequest
from app.models.design import DesignBrief
from app.models.enums import ApprovalStatus, DesignBriefStatus, Platform, PostStatus
from app.models.post import Post
from tests.conftest import create_org, register


async def test_changes_requested_are_listed_apart(client, db):
    admin = await register(client, "admin@acme.example.com")
    org_id = uuid.UUID((await create_org(admin))["id"])

    def post(title: str, status: PostStatus) -> Post:
        p = Post(organization_id=org_id, platform=Platform.LINKEDIN, title=title, status=status)
        db.add(p)
        return p

    draft = post("Fresh draft", PostStatus.DRAFT)
    post("Never reviewed", PostStatus.DRAFT)
    copy_back = post("Copy sent back", PostStatus.DRAFT)
    design_back = post("Design sent back", PostStatus.CHANGES_REQUESTED)
    designing = post("Being designed", PostStatus.DESIGN_IN_PROGRESS)
    await db.flush()
    # Copy-stage "changes requested" returns the post to DRAFT; the request keeps the decision.
    db.add_all(
        [
            ApprovalRequest(
                organization_id=org_id,
                post_id=copy_back.id,
                post_version=1,
                status=ApprovalStatus.CHANGES_REQUESTED,
            ),
            # An older request that was sent back, then approved: no longer pending changes.
            ApprovalRequest(
                organization_id=org_id,
                post_id=draft.id,
                post_version=1,
                status=ApprovalStatus.CHANGES_REQUESTED,
            ),
        ]
    )
    # Saved apart so the requests get distinct timestamps (now() is per transaction).
    await db.commit()
    db.add(
        ApprovalRequest(
            organization_id=org_id, post_id=draft.id, post_version=2, status=ApprovalStatus.REJECTED
        )
    )
    for p in (design_back, designing):
        db.add(
            DesignBrief(
                organization_id=org_id,
                post_id=p.id,
                format="single_image",
                status=DesignBriefStatus.IN_PROGRESS,
            )
        )
    await db.commit()

    async def titles(url: str) -> tuple[set[str], dict]:
        body = (await admin.get(url)).json()
        names = {i["title"] if "title" in i else i["post"]["title"] for i in body["items"]}
        return names, body["counts"]

    drafts, counts = await titles("/api/v1/content?status=drafts")
    assert drafts == {"Fresh draft", "Never reviewed"}
    changes, _ = await titles("/api/v1/content?status=changes")
    assert changes == {"Copy sent back", "Design sent back"}
    assert counts["drafts"] == 2 and counts["changes"] == 2 and counts["all"] == 5

    todo, counts = await titles("/api/v1/design/tasks?status=todo")
    assert todo == {"Being designed"}
    sent_back, _ = await titles("/api/v1/design/tasks?status=changes")
    assert sent_back == {"Design sent back"}
    assert counts["todo"] == 1 and counts["changes"] == 1


async def test_only_a_post_with_nothing_written_can_be_deleted(client, db):
    admin = await register(client, "admin@acme.example.com")
    org_id = uuid.UUID((await create_org(admin))["id"])
    failed = Post(
        organization_id=org_id, platform=Platform.X, title="Failed", status=PostStatus.DRAFT
    )
    written = Post(
        organization_id=org_id,
        platform=Platform.X,
        title="Written",
        status=PostStatus.DRAFT,
        current_version=1,
    )
    db.add_all([failed, written])
    await db.commit()

    assert (await admin.delete(f"/api/v1/content/{written.id}")).status_code == 409
    assert (await admin.delete(f"/api/v1/content/{failed.id}")).status_code == 204
    assert (await admin.get(f"/api/v1/content/{failed.id}")).status_code == 404
    assert (await admin.get(f"/api/v1/content/{written.id}")).status_code == 200


async def test_design_approval_status_lists_submitted_and_approved(client, db):
    admin = await register(client, "admin@acme.example.com")
    org_id = uuid.UUID((await create_org(admin))["id"])
    for title, post_status, brief_status in [
        ("Waiting", PostStatus.PENDING_APPROVAL, DesignBriefStatus.SUBMITTED),
        ("Approved", PostStatus.FINAL, DesignBriefStatus.COMPLETED),
        ("Designing", PostStatus.DESIGN_IN_PROGRESS, DesignBriefStatus.IN_PROGRESS),
    ]:
        p = Post(organization_id=org_id, platform=Platform.X, title=title, status=post_status)
        db.add(p)
        await db.flush()
        db.add(
            DesignBrief(
                organization_id=org_id, post_id=p.id, format="single_image", status=brief_status
            )
        )
    await db.commit()
    body = (await admin.get("/api/v1/design/tasks?status=approval")).json()
    assert {i["post"]["title"] for i in body["items"]} == {"Waiting", "Approved"}
    assert body["counts"]["approval"] == 2
