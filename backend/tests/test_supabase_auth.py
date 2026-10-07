import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.config import Settings, get_settings
from app.core.supabase import jwks_cache
from app.main import app

SUPABASE_URL = "https://testproject.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


class FakeSupabase:
    """Signs tokens like Supabase Auth and serves its JWKS."""

    def __init__(self) -> None:
        self.keys: dict[str, ec.EllipticCurvePrivateKey] = {}
        self.jwks_fetches = 0
        self.rotate()

    def rotate(self) -> str:
        kid = uuid.uuid4().hex
        self.keys[kid] = ec.generate_private_key(ec.SECP256R1())
        self.current = kid
        return kid

    def jwks(self) -> dict:
        keys = []
        for kid, private in self.keys.items():
            jwk = json.loads(ECAlgorithm.to_jwk(private.public_key()))
            keys.append({**jwk, "kid": kid, "alg": "ES256", "use": "sig"})
        return {"keys": keys}

    def token(
        self,
        email: str,
        *,
        sub: str | None = None,
        name: str | None = "Sam Supabase",
        expires_in: int = 3600,
        aud: str = "authenticated",
        iss: str = ISSUER,
        kid: str | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": sub or str(uuid.uuid5(uuid.NAMESPACE_DNS, email)),
            "email": email,
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + expires_in,
            "role": "authenticated",
            "user_metadata": {"full_name": name} if name else {},
        }
        kid = kid or self.current
        return jwt.encode(claims, self.keys[kid], algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def supabase(monkeypatch):
    fake = FakeSupabase()

    async def refresh(self, url: str) -> None:
        assert url == f"{ISSUER}/.well-known/jwks.json"
        fake.jwks_fetches += 1
        self._keys = {k["kid"]: jwt.PyJWK(k) for k in fake.jwks()["keys"]}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr(type(jwks_cache), "_refresh", refresh)
    jwks_cache.clear()
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_provider="supabase",
        supabase_url=SUPABASE_URL,
        supabase_anon_key="sb_publishable_test",
        supabase_jwt_secret="legacy-shared-secret-for-hs256-tokens",
        trend_scheduler_enabled=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield fake
    app.dependency_overrides.pop(get_settings, None)
    jwks_cache.clear()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_config_exposes_public_supabase_settings(client, supabase):
    assert (await client.get("/api/v1/auth/config")).json() == {
        "provider": "supabase",
        "password_reset": True,
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": "sb_publishable_test",
    }


async def test_es256_token_provisions_and_links_user(client, supabase):
    token = supabase.token("Sam@Example.com")
    me = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "sam@example.com"
    assert me.json()["name"] == "Sam Supabase"

    again = await client.get("/api/v1/auth/me", headers=bearer(supabase.token("sam@example.com")))
    assert again.json()["id"] == me.json()["id"]
    assert supabase.jwks_fetches == 1  # keys are cached

    org = await client.post(
        "/api/v1/organizations", json={"name": "Supa Co"}, headers=bearer(token)
    )
    assert org.status_code == 201
    assert (await client.get("/api/v1/auth/me", headers=bearer(token))).json()["role"] == "admin"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expires_in": -10},
        {"aud": "anon"},
        {"iss": "https://evil.supabase.co/auth/v1"},
    ],
)
async def test_invalid_tokens_are_rejected(client, supabase, kwargs):
    resp = await client.get(
        "/api/v1/auth/me", headers=bearer(supabase.token("x@example.com", **kwargs))
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_forged_signature_is_rejected(client, supabase):
    forger = ec.generate_private_key(ec.SECP256R1())
    claims = jwt.decode(supabase.token("x@example.com"), options={"verify_signature": False})
    forged = jwt.encode(claims, forger, algorithm="ES256", headers={"kid": supabase.current})
    assert (await client.get("/api/v1/auth/me", headers=bearer(forged))).status_code == 401
    unknown_kid = jwt.encode(claims, forger, algorithm="ES256", headers={"kid": "nope"})
    assert (await client.get("/api/v1/auth/me", headers=bearer(unknown_kid))).status_code == 401


async def test_key_rotation_refreshes_jwks(client, supabase):
    assert (
        await client.get("/api/v1/auth/me", headers=bearer(supabase.token("a@example.com")))
    ).status_code == 200
    supabase.rotate()
    resp = await client.get("/api/v1/auth/me", headers=bearer(supabase.token("a@example.com")))
    assert resp.status_code == 200
    assert supabase.jwks_fetches == 2


async def test_legacy_hs256_tokens(client, supabase):
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "legacy@example.com",
            "aud": "authenticated",
            "iss": ISSUER,
            "exp": now + 600,
        },
        "legacy-shared-secret-for-hs256-tokens",
        algorithm="HS256",
    )
    assert (await client.get("/api/v1/auth/me", headers=bearer(token))).status_code == 200
    bad = jwt.encode(
        {"sub": "x", "exp": now + 600, "aud": "authenticated", "iss": ISSUER},
        "wrong-secret-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )
    assert (await client.get("/api/v1/auth/me", headers=bearer(bad))).status_code == 401


async def test_password_endpoints_disabled(client, supabase):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"}
    )
    assert resp.status_code == 403
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "correct-horse-battery", "full_name": "A"},
    )
    assert resp.status_code == 403


async def test_invites_with_supabase_identities(client, supabase):
    admin = bearer(supabase.token("admin@example.com", name="Ada Admin"))
    await client.get("/api/v1/auth/me", headers=admin)
    org = (
        await client.post("/api/v1/organizations", json={"name": "Supa Co"}, headers=admin)
    ).json()
    invite = await client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "dee@example.com", "role": "creator"},
        headers=admin,
    )
    raw = invite.json()["invite_url"].rsplit("/", 1)[1]

    # Someone else holding the link can't take the seat.
    intruder = bearer(supabase.token("mallory@example.com"))
    resp = await client.post(
        "/api/v1/auth/invites/accept", json={"token": raw, "full_name": "M"}, headers=intruder
    )
    assert resp.status_code == 403

    invitee = bearer(supabase.token("dee@example.com", name="Dee Designer"))
    resp = await client.post(
        "/api/v1/auth/invites/accept", json={"token": raw, "full_name": "Dee"}, headers=invitee
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "creator"
    assert "set-cookie" not in resp.headers  # Supabase owns the session
