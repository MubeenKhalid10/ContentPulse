from tests.conftest import create_org, register
from tests.test_alignment import internet  # noqa: F401  (fixture)
from tests.test_design import design_ai  # noqa: F401  (fixture)


async def test_summary_for_new_organization(client):
    admin = await register(client, "admin@acme.example.com", "Ada Admin")
    org = await create_org(admin)

    resp = await admin.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trends_today"] == 0
    assert body["pending_approval"] == 0
    assert body["recent_activity"][0]["action"] == "ORGANIZATION_CREATED"
    assert body["recent_activity"][0]["user_name"] == "Ada Admin"

    # Explicit org selection works for members.
    resp = await admin.get("/api/v1/dashboard/summary", headers={"X-Organization-Id": org["id"]})
    assert resp.status_code == 200


async def test_summary_without_organization(client):
    user = await register(client, "lonely@acme.example.com")
    resp = await user.get("/api/v1/dashboard/summary")
    assert resp.status_code == 404


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_overview_counts_the_real_journey(client, internet, design_ai):
    from tests.test_alignment import setup_org
    from tests.test_design import in_design

    admin, org = await setup_org(client)
    post, task = await in_design(admin, org)

    resp = await admin.get("/api/v1/dashboard/overview?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 7
    for key in ("trends_discovered", "posts_generated", "relevant_trends", "approved_posts"):
        metric = body[key]
        assert len(metric["series"]) == 7
        assert sum(metric["series"]) == metric["value"]  # the daily series adds up
        assert metric["previous"] == 0  # nothing before this test's data
    assert body["trends_discovered"]["value"] >= 1
    assert body["posts_generated"]["value"] >= 1
    assert body["platform_breakdown"][post["platform"]] >= 1
    assert body["pipeline"]["design"] >= 1 and set(body["pipeline"]) == {
        "draft", "design", "approval", "changes", "ready"
    }
    assert body["recent_posts"][0]["id"] == post["id"]
    trending = body["trending"]
    assert trending and all(t["topic"] for t in trending)
    scores = [t["opportunity_score"] for t in trending if t["opportunity_score"] is not None]
    assert scores == sorted(scores, reverse=True)

    month = (await admin.get("/api/v1/dashboard/overview?days=30")).json()
    assert month["days"] == 30 and len(month["posts_generated"]["series"]) == 30
    odd = (await admin.get("/api/v1/dashboard/overview?days=12")).json()
    assert odd["days"] == 7  # only 7, 30 or 90


async def test_overview_for_new_organization(client):
    admin = await register(client, "fresh@acme.example.com", "Fay Fresh")
    await create_org(admin)
    body = (await admin.get("/api/v1/dashboard/overview")).json()
    assert body["trends_discovered"] == {"value": 0, "previous": 0, "series": [0] * 7}
    assert body["trending"] == [] and body["recent_posts"] == []
    assert body["pending_approval"] == 0
