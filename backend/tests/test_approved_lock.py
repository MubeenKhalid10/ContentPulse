"""Approved work is locked: approved copy and approved designs can't be
edited until an admin explicitly asks for changes."""

import uuid

from sqlalchemy import select

from app.models.approval import ApprovalRequest
from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import (
    ApprovalStatus,
    DesignBriefStatus,
    Platform,
    PostStatus,
    VersionSource,
)
from app.models.post import Post, PostVersion
from tests.conftest import add_member, create_org, register

API = "/api/v1/content"


async def setup(client, db):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    creator = await add_member(client, admin, org["id"], "creator@acme.example.com", "creator")
    return admin, creator, uuid.UUID(org["id"])


async def make_post(db, org_id, status: PostStatus, *, creative: bool = False) -> Post:
    post = Post(
        organization_id=org_id,
        platform=Platform.LINKEDIN,
        title="Launch post",
        status=status,
        current_version=1,
    )
    db.add(post)
    await db.flush()
    db.add(
        PostVersion(
            organization_id=org_id,
            post_id=post.id,
            version_number=1,
            hook="Hook",
            body="Body",
            cta="CTA",
            source=VersionSource.MANUAL,
        )
    )
    if creative:
        db.add(
            CreativeAsset(
                organization_id=org_id,
                post_id=post.id,
                version=1,
                file_name="a.png",
                file_type="image/png",
                file_size=10,
                storage_key=f"k/{uuid.uuid4().hex}.png",
            )
        )
    await db.commit()
    return post


async def edit(actor, post_id) -> int:
    resp = await actor.patch(f"{API}/{post_id}", json={"base_version": 1, "body": "New body"})
    return resp.status_code


async def editable(actor, post_id) -> bool:
    return (await actor.get(f"{API}/{post_id}")).json()["editable"]


async def test_copy_locks_once_approved_and_only_an_admin_reopens_it(client, db):
    admin, creator, org_id = await setup(client, db)
    draft = await make_post(db, org_id, PostStatus.DRAFT)
    assert await editable(creator, draft.id) and await edit(creator, draft.id) == 200

    designing = await make_post(db, org_id, PostStatus.DESIGN_PENDING)
    assert not await editable(creator, designing.id)
    resp = await creator.patch(f"{API}/{designing.id}", json={"base_version": 1, "body": "x"})
    assert resp.status_code == 409 and "locked" in resp.json()["error"]["message"]
    assert (await creator.post(f"{API}/{designing.id}/regenerate", json={})).status_code == 409

    # Taking it back from design reopens approved copy: admins only.
    assert (await creator.post(f"{API}/{designing.id}/back-to-draft")).status_code == 403
    resp = await admin.post(f"{API}/{designing.id}/back-to-draft")
    assert resp.status_code == 200 and resp.json()["editable"]


async def test_change_scope_decides_what_reopens(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.PENDING_APPROVAL, creative=True)
    request = ApprovalRequest(
        organization_id=org_id, post_id=post.id, post_version=1, creative_version=1
    )
    db.add(request)
    await db.commit()

    resp = await admin.post(
        f"/api/v1/approvals/{request.id}/request-changes",
        json={"comment": "Only the image needs work.", "scope": "design"},
    )
    assert resp.status_code == 200, resp.text
    assert not await editable(creator, post.id)  # design-only: the copy stays locked
    assert await edit(creator, post.id) == 409


async def test_admin_reopens_a_final_post(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.FINAL, creative=True)
    request = ApprovalRequest(
        organization_id=org_id,
        post_id=post.id,
        post_version=1,
        creative_version=1,
        status=ApprovalStatus.APPROVED,
    )
    brief = DesignBrief(
        organization_id=org_id,
        post_id=post.id,
        format="single_image",
        status=DesignBriefStatus.COMPLETED,
    )
    db.add_all([request, brief])
    await db.commit()

    assert not await editable(creator, post.id) and await edit(creator, post.id) == 409
    body = {"comment": "Fix the date in the copy.", "scope": "copy"}
    assert (
        await creator.post(f"/api/v1/approvals/{request.id}/reopen", json=body)
    ).status_code == 403

    resp = await admin.post(f"/api/v1/approvals/{request.id}/reopen", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "changes_requested"
    detail = (await creator.get(f"{API}/{post.id}")).json()
    assert detail["status"] == "changes_requested" and detail["editable"]
    assert await edit(creator, post.id) == 200
    await db.refresh(brief)
    assert brief.status == DesignBriefStatus.COMPLETED  # copy only: the design stays closed

    # Already reopened: can't be reopened twice.
    assert (
        await admin.post(f"/api/v1/approvals/{request.id}/reopen", json=body)
    ).status_code == 409


async def test_admin_reopens_a_final_design(client, db):
    admin, creator, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.FINAL, creative=True)
    request = ApprovalRequest(
        organization_id=org_id,
        post_id=post.id,
        post_version=1,
        creative_version=1,
        status=ApprovalStatus.APPROVED,
    )
    brief = DesignBrief(
        organization_id=org_id,
        post_id=post.id,
        format="single_image",
        status=DesignBriefStatus.COMPLETED,
    )
    db.add_all([request, brief])
    await db.commit()

    resp = await admin.post(
        f"/api/v1/approvals/{request.id}/reopen",
        json={"comment": "Use the new logo.", "scope": "design"},
    )
    assert resp.status_code == 200, resp.text
    await db.refresh(brief)
    assert brief.status == DesignBriefStatus.IN_PROGRESS
    assert not await editable(creator, post.id)


async def test_admin_reopens_approved_copy_during_design(client, db):
    admin, _, org_id = await setup(client, db)
    post = await make_post(db, org_id, PostStatus.DESIGN_IN_PROGRESS)
    request = ApprovalRequest(
        organization_id=org_id, post_id=post.id, post_version=1, status=ApprovalStatus.APPROVED
    )
    brief = DesignBrief(
        organization_id=org_id,
        post_id=post.id,
        format="single_image",
        status=DesignBriefStatus.IN_PROGRESS,
    )
    db.add_all([request, brief])
    await db.commit()

    resp = await admin.post(
        f"/api/v1/approvals/{request.id}/reopen", json={"comment": "Change the hook."}
    )
    assert resp.status_code == 200, resp.text
    await db.refresh(post)
    await db.refresh(brief)
    assert post.status == PostStatus.DRAFT and brief.status == DesignBriefStatus.CANCELLED
    assert await db.scalar(
        select(ApprovalRequest.status).where(ApprovalRequest.id == request.id)
    ) == (ApprovalStatus.CHANGES_REQUESTED)
