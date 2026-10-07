from tests.conftest import PASSWORD, register


async def test_register_returns_session_and_me(client):
    actor = await register(client, "Ada@Example.com", "Ada Lovelace")
    assert actor.user["email"] == "ada@example.com"  # normalized
    assert actor.user["organization_id"] is None
    assert actor.user["permissions"] == []

    resp = await actor.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Ada Lovelace"


async def test_register_sets_httponly_cookie(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "cookie@example.com", "password": PASSWORD, "full_name": "C"},
    )
    assert "httponly" in resp.headers["set-cookie"].lower()
    # The cookie alone authenticates subsequent requests.
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_duplicate_email_conflicts(client):
    await register(client, "dup@example.com")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@example.com", "password": PASSWORD, "full_name": "Again"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_login_success_and_failure(client):
    await register(client, "login@example.com")
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    for email, password in [
        ("login@example.com", "wrong-password"),
        ("nobody@example.com", PASSWORD),
    ]:
        bad = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert bad.status_code == 401
        # Same message whether or not the account exists.
        assert bad.json() == {
            "error": {"code": "UNAUTHORIZED", "message": "Invalid email or password."}
        }


async def test_me_requires_authentication(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_validation_errors_use_envelope(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "full_name": ""},
    )
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in error["details"]}
    assert fields == {"email", "password", "full_name"}


async def test_logout_clears_cookie(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bye@example.com", "password": PASSWORD, "full_name": "Bye"},
    )
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
