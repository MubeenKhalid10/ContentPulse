from tests.conftest import create_org, register


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
