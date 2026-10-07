from tests.conftest import add_member, create_org, register

API = "/api/v1/organizations"


async def test_create_organization_makes_creator_admin(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin, "Acme Software Ltd.")
    assert org["slug"] == "acme-software-ltd"
    assert org["website_url"] == "https://acme.example.com/"

    me = (await admin.get("/api/v1/auth/me")).json()
    assert me["organization_id"] == org["id"]
    assert me["role"] == "admin"
    assert "users.manage" in me["permissions"]

    # Defaults are provisioned alongside the organization.
    settings = (await admin.get(f"{API}/{org['id']}/settings")).json()
    assert settings["default_timezone"] == "Europe/London"
    assert settings["trend_frequency"] == "daily"
    brand = (await admin.get(f"{API}/{org['id']}/brand")).json()
    assert brand["forbidden_terms"] == []


async def test_slugs_are_unique(client):
    a = await register(client, "a@acme.example.com")
    first = await create_org(a, "Same Name")
    second = await create_org(a, "Same Name")
    assert first["slug"] == "same-name"
    assert second["slug"].startswith("same-name-") and second["slug"] != first["slug"]


async def test_patch_updates_only_sent_fields_and_audits_diff(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)

    resp = await admin.patch(f"{API}/{org['id']}", json={"industry": "Software"})
    assert resp.status_code == 200
    assert resp.json()["industry"] == "Software"
    assert resp.json()["name"] == "Acme Software"

    logs = (await admin.get(f"{API}/{org['id']}/audit-logs")).json()
    assert [entry["action"] for entry in logs] == ["ORGANIZATION_UPDATED", "ORGANIZATION_CREATED"]
    assert logs[0]["old_value"] == {"industry": None}
    assert logs[0]["new_value"] == {"industry": "Software"}

    # A no-op PATCH does not create an audit entry.
    await admin.patch(f"{API}/{org['id']}", json={"industry": "Software"})
    assert len((await admin.get(f"{API}/{org['id']}/audit-logs")).json()) == 2


async def test_patch_rejects_null_for_required_fields(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    resp = await admin.patch(f"{API}/{org['id']}", json={"name": None})
    assert resp.status_code == 422
    resp = await admin.patch(f"{API}/{org['id']}", json={"timezone": "Mars/Olympus"})
    assert resp.status_code == 422
    # Nullable fields can be cleared.
    resp = await admin.patch(f"{API}/{org['id']}", json={"website_url": None})
    assert resp.status_code == 200 and resp.json()["website_url"] is None


async def test_settings_and_brand_updates(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)

    resp = await admin.patch(
        f"{API}/{org['id']}/settings",
        json={
            "target_markets": ["USA", "UK"],
            "enabled_platforms": ["linkedin", "x"],
            "trend_frequency": "hourly",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled_platforms"] == ["linkedin", "x"]

    bad = await admin.patch(f"{API}/{org['id']}/settings", json={"enabled_platforms": ["myspace"]})
    assert bad.status_code == 422

    resp = await admin.patch(
        f"{API}/{org['id']}/brand",
        json={"brand_voice": "Confident, practical", "forbidden_terms": ["synergy"]},
    )
    assert resp.status_code == 200
    assert resp.json()["forbidden_terms"] == ["synergy"]


async def test_services_crud(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    base = f"{API}/{org['id']}/services"

    created = await admin.post(base, json={"name": "AI Solutions", "category": "AI"})
    assert created.status_code == 201
    service_id = created.json()["id"]
    await admin.post(base, json={"name": "Workflow Automator", "kind": "product"})

    listing = (await admin.get(base)).json()
    assert {s["name"] for s in listing} == {"AI Solutions", "Workflow Automator"}

    patched = await admin.patch(f"{base}/{service_id}", json={"active": False})
    assert patched.json()["active"] is False

    assert (await admin.delete(f"{base}/{service_id}")).status_code == 204
    assert (await admin.delete(f"{base}/{service_id}")).status_code == 404


async def test_tenant_isolation(client):
    alice = await register(client, "alice@a.example.com")
    bob = await register(client, "bob@b.example.com")
    org_a = await create_org(alice, "Org A")
    org_b = await create_org(bob, "Org B")
    service = (await alice.post(f"{API}/{org_a['id']}/services", json={"name": "Secret"})).json()

    # Non-members get 404, not 403, so org ids cannot be probed.
    for url in [
        f"{API}/{org_a['id']}",
        f"{API}/{org_a['id']}/services",
        f"{API}/{org_a['id']}/brand",
        f"{API}/{org_a['id']}/members",
    ]:
        resp = await bob.get(url)
        assert resp.status_code == 404, url
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    # Using his own org in the path does not unlock another org's service id.
    resp = await bob.patch(f"{API}/{org_b['id']}/services/{service['id']}", json={"name": "Pwned"})
    assert resp.status_code == 404

    # The active-org header cannot be used to switch into a foreign org either.
    resp = await bob.get("/api/v1/dashboard/summary", headers={"X-Organization-Id": org_a["id"]})
    assert resp.status_code == 404

    listing = (await bob.get(API)).json()
    assert [o["id"] for o in listing] == [org_b["id"]]


async def test_role_permissions_enforced(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    viewer = await add_member(client, admin, org["id"], "viewer@acme.example.com", "viewer")
    manager = await add_member(client, admin, org["id"], "cm@acme.example.com", "creator")

    # Everyone can read.
    for actor in (viewer, manager):
        assert (await actor.get(f"{API}/{org['id']}/brand")).status_code == 200

    # Only admins write organization data and see the audit history.
    for actor in (viewer, manager):
        resp = await actor.patch(f"{API}/{org['id']}/brand", json={"tone": "Edgy"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"
        assert (await actor.get(f"{API}/{org['id']}/audit-logs")).status_code == 403
        resp = await actor.post(
            f"{API}/{org['id']}/invitations", json={"email": "x@acme.example.com", "role": "admin"}
        )
        assert resp.status_code == 403
