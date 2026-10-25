"""Admins can delete posts (at any stage), post plans and a post's design;
nobody else can. Rows are built directly so these tests don't depend on
trend discovery or the AI."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.models.design import CreativeAsset, DesignBrief
from app.models.enums import (
    DesignBriefStatus,
    Platform,
    PostStatus,
    StrategyStatus,
    TopicStatus,
    TrendStatus,
    VersionSource,
)
from app.models.post import Post, PostVersion
from app.models.topic import ContentStrategy, TopicCandidate
from app.models.trend import Trend
from tests.conftest import add_member, create_org, register

POSTS = "/api/v1/content"
TASKS = "/api/v1/design/tasks"


async def make_post(db, org_id: str, admin, status: PostStatus, *, files: int = 0) -> dict:
    """A topic with a plan, a written post in `status`, its design task and `files` creatives."""
    org = uuid.UUID(org_id)
    topic = TopicCandidate(organization_id=org, title="Agents", status=TopicStatus.SHORTLISTED)
    db.add(topic)
    await db.flush()
    strategy = ContentStrategy(
        organization_id=org,
        topic_id=topic.id,
        platform=Platform.LINKEDIN,
        post_type="Post",
        status=StrategyStatus.APPROVED,
    )
    db.add(strategy)
    await db.flush()
    post = Post(
        organization_id=org,
        topic_id=topic.id,
        content_strategy_id=strategy.id,
        platform=Platform.LINKEDIN,
        title="Agents post",
        status=status,
        current_version=1,
    )
    db.add(post)
    await db.flush()
    db.add(
        PostVersion(
            organization_id=org,
            post_id=post.id,
            version_number=1,
            hook="Hook",
            body="Body",
            source=VersionSource.MANUAL,
        )
    )
    brief = DesignBrief(
        organization_id=org, post_id=post.id, format="single_image", status=DesignBriefStatus.OPEN
    )
    db.add(brief)
    await db.flush()
    for position in range(files):
        db.add(
            CreativeAsset(
                organization_id=org,
                post_id=post.id,
                design_brief_id=brief.id,
                file_name=f"slide-{position}.png",
                file_type="image/png",
                file_size=10,
                storage_key=f"orgs/{org}/missing-{position}.png",
                version=1,
                position=position,
            )
        )
    await db.commit()
    return {
        "post": str(post.id),
        "task": str(brief.id),
        "topic": str(topic.id),
        "plan": str(strategy.id),
    }


async def team(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    creator = await add_member(client, admin, org["id"], "cy@acme.example.com", "creator")
    return admin, creator, org


async def test_admin_deletes_a_post_at_any_stage_with_its_design(client, db):
    admin, creator, org = await team(client)
    ids = await make_post(db, org["id"], admin, PostStatus.PENDING_APPROVAL, files=2)

    # A writer can only delete a post whose writing failed.
    assert (await creator.delete(f"{POSTS}/{ids['post']}")).status_code == 409
    assert (await admin.get(f"{POSTS}/{ids['post']}")).status_code == 200

    assert (await admin.delete(f"{POSTS}/{ids['post']}")).status_code == 204
    assert (await admin.get(f"{POSTS}/{ids['post']}")).status_code == 404
    assert (await admin.get(f"{TASKS}/{ids['task']}")).status_code == 404
    db.expire_all()
    left = await db.scalar(
        select(func.count())
        .select_from(CreativeAsset)
        .where(CreativeAsset.post_id == uuid.UUID(ids["post"]))
    )
    assert left == 0


async def test_deleting_a_plan_keeps_its_posts_and_is_admin_only(client, db):
    admin, creator, org = await team(client)
    ids = await make_post(db, org["id"], admin, PostStatus.DRAFT)
    url = f"/api/v1/topics/{ids['topic']}/strategies/{ids['plan']}"

    assert (await creator.delete(url)).status_code == 403
    assert (await admin.delete(url)).status_code == 204

    plans = (await admin.get(f"/api/v1/topics/{ids['topic']}/strategies")).json()
    assert all(p["id"] != ids["plan"] for p in plans)
    kept = (await admin.get(f"{POSTS}/{ids['post']}")).json()
    assert kept["id"] == ids["post"] and kept["content_strategy_id"] is None


async def test_admin_deletes_a_design_while_it_is_being_made(client, db):
    admin, creator, org = await team(client)
    ids = await make_post(db, org["id"], admin, PostStatus.DESIGN_UPLOADED, files=2)

    assert (await creator.delete(f"{TASKS}/{ids['task']}/creatives")).status_code == 403
    resp = await admin.delete(f"{TASKS}/{ids['task']}/creatives")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["creatives"] == [] and body["post"]["status"] == "design_in_progress"

    # Nothing left to delete.
    assert (await admin.delete(f"{TASKS}/{ids['task']}/creatives")).status_code == 404


async def test_a_design_waiting_for_approval_cannot_be_deleted(client, db):
    admin, _, org = await team(client)
    ids = await make_post(db, org["id"], admin, PostStatus.PENDING_APPROVAL, files=1)
    assert (await admin.delete(f"{TASKS}/{ids['task']}/creatives")).status_code == 409


async def test_attention_counts_for_the_sidebar(client, db):
    admin, _, org = await team(client)
    await make_post(db, org["id"], admin, PostStatus.CONTENT_REVIEW)
    await make_post(db, org["id"], admin, PostStatus.PENDING_APPROVAL)
    await make_post(db, org["id"], admin, PostStatus.DESIGN_PENDING)
    await make_post(db, org["id"], admin, PostStatus.CHANGES_REQUESTED)
    await make_post(db, org["id"], admin, PostStatus.FINAL)
    body = (await admin.get("/api/v1/dashboard/attention")).json()
    # Four topics are shortlisted (make_post adds one each), none are "to review".
    assert body == {"to_review": 0, "design": 2, "approvals": 2}


async def test_topic_detail_can_leave_out_the_full_trend(client, db):
    admin, _, org = await team(client)
    ids = await make_post(db, org["id"], admin, PostStatus.DRAFT)
    now = datetime.now(UTC)
    trend = Trend(
        organization_id=uuid.UUID(org["id"]),
        canonical_key="agents",
        topic="Agents",
        status=TrendStatus.SHORTLISTED,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(trend)
    await db.flush()
    await db.execute(
        update(TopicCandidate)
        .where(TopicCandidate.id == uuid.UUID(ids["topic"]))
        .values(trend_id=trend.id)
    )
    await db.commit()

    full = (await admin.get(f"/api/v1/topics/{ids['topic']}")).json()
    lean = (await admin.get(f"/api/v1/topics/{ids['topic']}?include_trend=false")).json()
    assert full["trend"]["id"] == str(trend.id)
    assert lean["trend"] is None and lean["id"] == full["id"]
    assert [p["id"] for p in lean["strategies"]] == [p["id"] for p in full["strategies"]]
