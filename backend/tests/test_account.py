"""Settings > Your account: name and password for the signed-in user."""

from tests.conftest import register

PASSWORD = "correct-horse-battery"


async def test_update_own_name(client):
    me = await register(client, "nina@example.com", "Nina")
    resp = await me.patch("/api/v1/auth/me", json={"full_name": "  Nina Novak  "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Nina Novak"
    assert (await me.get("/api/v1/auth/me")).json()["name"] == "Nina Novak"
    assert (await me.patch("/api/v1/auth/me", json={"full_name": ""})).status_code == 422


async def test_change_password(client):
    me = await register(client, "omar@example.com", "Omar")
    wrong = await me.post(
        "/api/v1/auth/password",
        json={"current_password": "not-my-password", "new_password": "a-brand-new-password"},
    )
    assert wrong.status_code == 422
    assert "current password" in wrong.json()["error"]["message"]

    same = await me.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
    )
    assert same.status_code == 422

    short = await me.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422

    ok = await me.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert ok.status_code == 204

    old = await client.post(
        "/api/v1/auth/login", json={"email": "omar@example.com", "password": PASSWORD}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "omar@example.com", "password": "a-brand-new-password"},
    )
    assert new.status_code == 200


async def test_account_endpoints_need_a_session(client):
    assert (await client.patch("/api/v1/auth/me", json={"full_name": "X"})).status_code == 401
    resp = await client.post(
        "/api/v1/auth/password", json={"current_password": "a", "new_password": "b" * 12}
    )
    assert resp.status_code == 401
