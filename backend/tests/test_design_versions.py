"""Using an earlier creative version: its files become the newest version,
the one reviewers see. The task is created directly (no AI pipeline)."""

import uuid

from app.models.design import DesignBrief
from app.models.enums import DesignBriefStatus, Platform, PostStatus
from app.models.post import Post
from tests.conftest import add_member, create_org, register
from tests.test_design import API, upload


async def task_in_design(client, db):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    post = Post(
        organization_id=uuid.UUID(org["id"]),
        platform=Platform.LINKEDIN,
        title="Versions",
        status=PostStatus.DESIGN_IN_PROGRESS,
    )
    db.add(post)
    await db.flush()
    brief = DesignBrief(
        organization_id=post.organization_id,
        post_id=post.id,
        format="single_image",
        status=DesignBriefStatus.IN_PROGRESS,
    )
    db.add(brief)
    await db.commit()
    return admin, org, str(brief.id)


async def add_version(actor, task_id: str, name: str) -> dict:
    key = await upload(actor, task_id, name)
    resp = await actor.post(
        f"{API}/{task_id}/assets", json={"files": [{"storage_key": key, "file_name": name}]}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_an_earlier_version_becomes_the_newest(client, db):
    admin, org, task_id = await task_in_design(client, db)
    await add_version(admin, task_id, "first.png")
    await add_version(admin, task_id, "second.png")

    creator = await add_member(client, admin, org["id"], "cleo@acme.example.com", "creator")
    resp = await creator.post(f"{API}/{task_id}/versions/1/use")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    newest, *older = body["creatives"]
    assert newest["version"] == 3 and [v["version"] for v in older] == [2, 1]
    assert [f["file_name"] for f in newest["files"]] == ["first.png"]
    assert newest["note"] == "Reused version 1"
    assert newest["uploaded_by"]["id"] == creator.user["id"]
    # Same stored file: it is served like the original.
    served = await client.get(newest["files"][0]["url"])
    assert served.status_code == 200

    # Already the newest; unknown version.
    assert (await admin.post(f"{API}/{task_id}/versions/3/use")).status_code == 409
    assert (await admin.post(f"{API}/{task_id}/versions/9/use")).status_code == 404

    # What gets submitted is the reused design.
    submitted = (await admin.post(f"{API}/{task_id}/submit")).json()
    assert submitted["post"]["status"] == "pending_approval"
    # Under review, the version can't be swapped.
    assert (await admin.post(f"{API}/{task_id}/versions/2/use")).status_code == 409


async def test_viewers_and_other_organizations_cannot_use_versions(client, db):
    admin, org, task_id = await task_in_design(client, db)
    await add_version(admin, task_id, "first.png")
    await add_version(admin, task_id, "second.png")

    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.post(f"{API}/{task_id}/versions/1/use")).status_code == 403

    outsider = await register(client, "out@other.example.com")
    await create_org(outsider, name="Other Co")
    assert (await outsider.post(f"{API}/{task_id}/versions/1/use")).status_code == 404
