import json
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from sqlalchemy import select

from app.core import supabase as supabase_module
from app.core.config import Settings, get_settings
from app.core.supabase import jwks_cache
from app.main import app

ORIGINAL_FETCH_AUTH_USER = supabase_module._fetch_auth_user
SUPABASE_URL = "https://testproject.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


class FakeSupabase:
    """Signs tokens like Supabase Auth and serves its JWKS and /auth/v1/user."""

    def __init__(self) -> None:
        self.keys: dict[str, ec.EllipticCurvePrivateKey] = {}
        self.jwks_fetches = 0
        self.confirmed: dict[str, bool] = {}  # subject -> email confirmed
        self.user_lookups = 0
        self.rotate()

    def user(self, token: str) -> dict:
        self.user_lookups += 1
        sub = jwt.decode(token, options={"verify_signature": False})["sub"]
        confirmed = self.confirmed.get(sub, True)
        return {"id": sub, "email_confirmed_at": "2026-11-01T00:00:00Z" if confirmed else None}

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
        email_verified: bool = True,
    ) -> str:
        now = int(time.time())
        sub = sub or str(uuid.uuid5(uuid.NAMESPACE_DNS, email))
        self.confirmed[sub] = email_verified
        claims = {
            "sub": sub,
            "email": email,
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + expires_in,
            "role": "authenticated",
            "user_metadata": {"full_name": name, "email_verified": email_verified}
            if name
            else {"email_verified": email_verified},
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

    async def fetch_user(token: str, settings: Settings) -> dict:
        return fake.user(token)

    monkeypatch.setattr(type(jwks_cache), "_refresh", refresh)
    monkeypatch.setattr(supabase_module, "_fetch_auth_user", fetch_user)
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
    # Exactly the public values: no JWT secret or other server-side setting.
    # Without TURNSTILE_SITE_KEY the field is null (the web app then explains
    # that the key is missing when Supabase requires a CAPTCHA).
    assert (await client.get("/api/v1/auth/config")).json() == {
        "provider": "supabase",
        "password_reset": True,
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": "sb_publishable_test",
        "turnstile_site_key": None,
        # Supabase confirms emails itself, so our own confirmation step is never asked for.
        "email_verification": False,
    }


async def test_config_exposes_the_public_turnstile_site_key(client, supabase, monkeypatch):
    settings = app.dependency_overrides[get_settings]()
    monkeypatch.setattr(settings, "turnstile_site_key", "0x4AAAAAAATestSiteKey")
    body = (await client.get("/api/v1/auth/config")).json()
    assert body["turnstile_site_key"] == "0x4AAAAAAATestSiteKey"
    assert "legacy-shared-secret" not in str(body)


async def test_local_mode_publishes_no_turnstile_key(client, monkeypatch):
    # A site key alone doesn't turn the CAPTCHA on in local mode: the server also needs
    # TURNSTILE_SECRET_KEY to check answers (see test_email_verification_captcha.py).
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "0x4AAAAAAATestSiteKey")
    body = (await client.get("/api/v1/auth/config")).json()
    assert body["provider"] == "local" and body["turnstile_site_key"] is None


async def test_unreachable_signing_keys_are_not_a_finished_session(client, supabase, monkeypatch):
    # A 401 signs the person out; failing to reach Supabase says nothing about the token.
    token = supabase.token("sam@example.com")
    jwks_cache.clear()

    async def unreachable(self, url):
        raise httpx.ConnectError("getaddrinfo failed")

    monkeypatch.setattr(type(jwks_cache), "_refresh", unreachable)
    response = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


async def test_es256_token_provisions_and_links_user(client, supabase):
    sub = str(uuid.uuid4())
    token = supabase.token("Sam@Example.com", sub=sub)
    me = await client.get("/api/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "sam@example.com"
    assert me.json()["name"] == "Sam Supabase"

    again = await client.get(
        "/api/v1/auth/me", headers=bearer(supabase.token("sam@example.com", sub=sub))
    )
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


async def test_verified_recreated_identity_relinks_existing_account(client, supabase):
    victim = bearer(supabase.token("victim@example.com", sub=str(uuid.uuid4())))
    original = await client.get("/api/v1/auth/me", headers=victim)
    assert original.status_code == 200

    # Supabase deletion followed by signup creates a new subject. The verified
    # email reclaims the same platform row and keeps its identity/data.
    recreated = bearer(supabase.token("victim@example.com", sub=str(uuid.uuid4())))
    resp = await client.get("/api/v1/auth/me", headers=recreated)
    assert resp.status_code == 200
    assert resp.json()["id"] == original.json()["id"]

    # A token without email verification still cannot claim the row.
    unverified = bearer(
        supabase.token("victim@example.com", sub=str(uuid.uuid4()), email_verified=False)
    )
    assert (await client.get("/api/v1/auth/me", headers=unverified)).status_code == 401


async def test_an_unverified_email_cannot_claim_an_existing_account(client, supabase, db):
    from app.models import User

    db.add(User(email="seat@example.com", auth_provider="supabase"))  # an invite placeholder
    await db.commit()

    unverified = bearer(supabase.token("seat@example.com", email_verified=False))
    assert (await client.get("/api/v1/auth/me", headers=unverified)).status_code == 401
    verified = bearer(supabase.token("seat@example.com"))
    assert (await client.get("/api/v1/auth/me", headers=verified)).status_code == 200


async def test_an_unconfirmed_new_identity_is_not_provisioned(client, supabase, db):
    from app.models import User

    # Holding the email first would let it accept that address's invites later.
    unverified = bearer(supabase.token("early@example.com", email_verified=False))
    resp = await client.get("/api/v1/auth/me", headers=unverified)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"].startswith("Confirm your email first")
    assert await db.scalar(select(User).where(User.email == "early@example.com")) is None


async def test_editable_metadata_cannot_vouch_for_the_email(client, supabase):
    # supabase.auth.updateUser lets a user set their own user_metadata.
    claims = jwt.decode(
        supabase.token("forger@example.com", email_verified=False),
        options={"verify_signature": False},
    )
    claims["user_metadata"]["email_verified"] = True
    token = jwt.encode(
        claims,
        supabase.keys[supabase.current],
        algorithm="ES256",
        headers={"kid": supabase.current},
    )
    assert (await client.get("/api/v1/auth/me", headers=bearer(token))).status_code == 401


async def test_confirmation_is_asked_once_per_identity(client, supabase):
    token = bearer(supabase.token("once@example.com"))
    for _ in range(3):
        assert (await client.get("/api/v1/auth/me", headers=token)).status_code == 200
    assert supabase.user_lookups == 1  # linked identities skip the lookup


async def test_unreachable_user_endpoint_is_not_a_finished_session(client, supabase, monkeypatch):
    monkeypatch.setattr(supabase_module, "_fetch_auth_user", ORIGINAL_FETCH_AUTH_USER)

    real_get = httpx.AsyncClient.get

    async def unreachable(self, url, **kw):
        if str(url).startswith(SUPABASE_URL):
            raise httpx.ConnectError("getaddrinfo failed")
        return await real_get(self, url, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "get", unreachable)
    resp = await client.get("/api/v1/auth/me", headers=bearer(supabase.token("x@example.com")))
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


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
