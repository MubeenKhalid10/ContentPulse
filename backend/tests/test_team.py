from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models.organization import OrganizationMember
from tests.conftest import PASSWORD, add_member, create_org, register

API = "/api/v1/organizations"


async def _invite(admin, org_id: str, email: str, role: str = "creator") -> str:
    resp = await admin.post(f"{API}/{org_id}/invitations", json={"email": email, "role": role})
    assert resp.status_code == 201, resp.text
    assert resp.json()["member"]["status"] == "invited"
    return resp.json()["invite_url"].rsplit("/", 1)[1]


async def test_invite_preview_and_accept_as_new_user(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    token = await _invite(admin, org["id"], "Designer@Acme.example.com")

    preview = await client.get(f"/api/v1/auth/invites/{token}")
    assert preview.status_code == 200
    assert preview.json()["email"] == "designer@acme.example.com"
    assert preview.json()["organization_name"] == "Acme Software"
    assert preview.json()["has_account"] is False

    # New users must choose a password.
    resp = await client.post(
        "/api/v1/auth/invites/accept", json={"token": token, "full_name": "Dee"}
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "Dee", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "creator"
    assert "design.upload" in resp.json()["permissions"]

    signed_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "designer@acme.example.com", "password": PASSWORD},
    )
    assert signed_in.status_code == 200, signed_in.text

    # Token is single-use.
    assert (await client.get(f"/api/v1/auth/invites/{token}")).status_code == 404

    members = (await admin.get(f"{API}/{org['id']}/members")).json()
    assert {(m["email"], m["status"]) for m in members} == {
        ("admin@acme.example.com", "active"),
        ("designer@acme.example.com", "active"),
    }


async def test_existing_account_must_prove_password(client):
    admin = await register(client, "admin@acme.example.com")
    await register(client, "existing@acme.example.com")
    org = await create_org(admin)
    token = await _invite(admin, org["id"], "existing@acme.example.com", "creator")

    assert (await client.get(f"/api/v1/auth/invites/{token}")).json()["has_account"] is True
    resp = await client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "X", "password": "wrong-password-123"},
    )
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "X", "password": PASSWORD},
    )
    assert resp.status_code == 200


async def test_admin_cannot_change_own_role(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    members = (await admin.get(f"{API}/{org['id']}/members")).json()
    admin_member = next(m for m in members if m["user_id"] == admin.user["id"])

    resp = await admin.patch(
        f"{API}/{org['id']}/members/{admin_member['id']}",
        json={"role": "creator"},
    )
    assert resp.status_code == 409
    assert "own role" in resp.json()["error"]["message"]


async def test_reinvite_replaces_token_and_expired_invites_fail(client, db):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    old_token = await _invite(admin, org["id"], "new@acme.example.com")
    new_token = await _invite(admin, org["id"], "new@acme.example.com", "creator")

    assert (await client.get(f"/api/v1/auth/invites/{old_token}")).status_code == 404
    assert (await client.get(f"/api/v1/auth/invites/{new_token}")).json()["role"] == "creator"

    await db.execute(
        update(OrganizationMember).values(invite_expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db.commit()
    resp = await client.get(f"/api/v1/auth/invites/{new_token}")
    assert resp.status_code == 410


async def test_cannot_invite_existing_member(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    resp = await admin.post(
        f"{API}/{org['id']}/invitations",
        json={"email": "admin@acme.example.com", "role": "creator"},
    )
    assert resp.status_code == 409


async def test_last_admin_cannot_be_demoted_disabled_or_removed(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    members = (await admin.get(f"{API}/{org['id']}/members")).json()
    me = members[0]["id"]

    for body in ({"role": "creator"}, {"status": "disabled"}):
        resp = await admin.patch(f"{API}/{org['id']}/members/{me}", json=body)
        assert resp.status_code == 409, body
    assert (await admin.delete(f"{API}/{org['id']}/members/{me}")).status_code == 409

    # Self-role changes remain blocked even when another admin exists.
    second_admin = await add_member(client, admin, org["id"], "admin2@acme.example.com", "admin")
    resp = await admin.patch(f"{API}/{org['id']}/members/{me}", json={"role": "creator"})
    assert resp.status_code == 409

    # A different admin can still change the first admin's role.
    second_members = (await admin.get(f"{API}/{org['id']}/members")).json()
    second_member_id = next(
        m["id"] for m in second_members if m["user_id"] == second_admin.user["id"]
    )
    resp = await admin.patch(
        f"{API}/{org['id']}/members/{second_member_id}", json={"role": "creator"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "creator"


async def test_disabled_member_loses_access(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    creator2 = await add_member(client, admin, org["id"], "creator2@acme.example.com", "creator")
    member_id = next(
        m["id"]
        for m in (await admin.get(f"{API}/{org['id']}/members")).json()
        if m["email"] == "creator2@acme.example.com"
    )

    resp = await admin.patch(f"{API}/{org['id']}/members/{member_id}", json={"status": "disabled"})
    assert resp.status_code == 200
    assert (await creator2.get(f"{API}/{org['id']}")).status_code == 404

    assert (await admin.delete(f"{API}/{org['id']}/members/{member_id}")).status_code == 204
    actions = [e["action"] for e in (await admin.get(f"{API}/{org['id']}/audit-logs")).json()]
    assert actions[:2] == ["MEMBER_REMOVED", "MEMBER_UPDATED"]
