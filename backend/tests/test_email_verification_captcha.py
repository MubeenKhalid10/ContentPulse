"""Local sign-in without Supabase: email confirmation and Cloudflare Turnstile."""

import httpx
import pytest

from app.core import captcha as captcha_module
from app.core import email as email_module
from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
)
from tests.conftest import PASSWORD, create_org, register

ORG = {"name": "Acme Software", "website_url": "https://acme.example.com", "timezone": "UTC"}


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(email_module, "_send_sync", lambda settings, message: sent.append(message))
    return sent


@pytest.fixture
def smtp_on(monkeypatch):
    """SMTP configured, so email verification is on (REQUIRE_EMAIL_VERIFICATION unset)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "ContentPulse <no-reply@example.com>")
    return settings


@pytest.fixture
def turnstile_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "turnstile_site_key", "site-key")
    monkeypatch.setattr(settings, "turnstile_secret_key", "secret-key")
    calls: list[tuple[str, str]] = []
    answers = {"success": True}

    async def fake_siteverify(token, remote_ip, _settings):
        calls.append((token, remote_ip))
        return {"success": answers["success"]}

    monkeypatch.setattr(captcha_module, "_siteverify", fake_siteverify)
    return calls, answers


def _link_token(message) -> str:
    body = message.get_body(preferencelist=("plain",)).get_content()
    return body.split("/verify-email#token=")[1].split()[0]


async def _sign_up(client, email="newbie@example.com", **extra):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "New Bie", **extra},
    )


# --- email verification ----------------------------------------------------------------


async def test_config_reports_verification_only_with_smtp(client, smtp_on):
    assert (await client.get("/api/v1/auth/config")).json()["email_verification"] is True


async def test_config_without_smtp_does_not_require_verification(client):
    assert (await client.get("/api/v1/auth/config")).json()["email_verification"] is False


async def test_new_account_must_confirm_before_creating_an_organization(client, smtp_on, outbox):
    r = await _sign_up(client)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email_verified"] is False
    assert len(outbox) == 1
    html = outbox[0].get_body(preferencelist=("html",)).get_content()
    assert "Confirm email" in html and "ContentPulse" in html
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    blocked = await client.post("/api/v1/organizations", json=ORG, headers=headers)
    assert blocked.status_code == 403, blocked.text

    # The link works without being signed in (another browser, a phone).
    client.cookies.clear()
    ok = await client.post("/api/v1/auth/email/verify", json={"token": _link_token(outbox[0])})
    assert ok.status_code == 204, ok.text

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["email_verified"] is True
    created = await client.post("/api/v1/organizations", json=ORG, headers=headers)
    assert created.status_code == 201, created.text

    # Using the link again is harmless.
    again = await client.post("/api/v1/auth/email/verify", json={"token": _link_token(outbox[0])})
    assert again.status_code == 204


async def test_unverified_account_can_still_sign_in_and_ask_for_a_new_link(client, smtp_on, outbox):
    await _sign_up(client)
    login = await client.post(
        "/api/v1/auth/login", json={"email": "newbie@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resend = await client.post("/api/v1/auth/email/resend", headers=headers)
    assert resend.status_code == 202
    assert len(outbox) == 2

    await client.post("/api/v1/auth/email/verify", json={"token": _link_token(outbox[1])})
    resend = await client.post("/api/v1/auth/email/resend", headers=headers)
    assert resend.status_code == 202
    assert len(outbox) == 2  # already confirmed: nothing more is sent


async def test_resend_needs_a_session(client, smtp_on):
    assert (await client.post("/api/v1/auth/email/resend")).status_code == 401


async def test_confirmation_links_are_not_sessions_or_reset_tokens(client, smtp_on, outbox):
    r = await _sign_up(client)
    user_id = r.json()["user"]["id"]
    token = _link_token(outbox[0])

    as_session = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert as_session.status_code == 401

    reset = create_password_reset_token(user_id, None, smtp_on)  # type: ignore[arg-type]
    for bad in (reset, create_access_token(user_id, smtp_on)[0], "x" * 30):  # type: ignore[arg-type]
        response = await client.post("/api/v1/auth/email/verify", json={"token": bad})
        assert response.status_code == 401


async def test_link_for_an_old_address_stops_working(client, smtp_on, db, outbox):
    from app.models.user import User

    r = await _sign_up(client)
    token = create_email_verification_token(
        r.json()["user"]["id"], "someone-else@example.com", smtp_on
    )  # type: ignore[arg-type]
    response = await client.post("/api/v1/auth/email/verify", json={"token": token})
    assert response.status_code == 401
    user = await db.get(User, r.json()["user"]["id"])
    assert user is not None and user.email_verified_at is None


async def test_without_smtp_nothing_changes(client):
    r = await _sign_up(client)
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    created = await client.post("/api/v1/organizations", json=ORG, headers=headers)
    assert created.status_code == 201


async def test_accepting_an_invitation_confirms_the_address(client, smtp_on, outbox):
    import re

    admin = await register(client, "admin@example.com")
    # The admin must confirm before creating the organization.
    await client.post("/api/v1/auth/email/verify", json={"token": _link_token(outbox[0])})
    org = await create_org(admin)
    invited = await admin.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "invitee@example.com", "role": "creator"},
    )
    assert invited.status_code == 201, invited.text
    body = outbox[-1].get_body(preferencelist=("plain",)).get_content()
    token = re.search(r"/invite/([\w-]+)", body).group(1)
    accepted = await client.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "full_name": "Invitee", "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["email_verified"] is True


def test_requiring_verification_without_smtp_is_a_configuration_error():
    with pytest.raises(ValueError, match="SMTP"):
        Settings(_env_file=None, auth_provider="local", require_email_verification=True)
    ok = Settings(
        _env_file=None,
        auth_provider="local",
        require_email_verification=True,
        smtp_host="smtp.example.com",
        smtp_from="a@example.com",
    )
    assert ok.email_verification_required is True


def test_supabase_mode_never_asks_for_our_verification():
    settings = Settings(
        _env_file=None,
        auth_provider="supabase",
        supabase_url="https://x.supabase.co",
        supabase_anon_key="anon",
        smtp_host="smtp.example.com",
        smtp_from="a@example.com",
    )
    assert settings.email_verification_required is False
    assert settings.captcha_enabled is False


# --- Turnstile -------------------------------------------------------------------------


async def test_config_hands_out_the_site_key_only_when_the_secret_is_set(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "turnstile_site_key", "site-key")
    assert (await client.get("/api/v1/auth/config")).json()["turnstile_site_key"] is None
    monkeypatch.setattr(settings, "turnstile_secret_key", "secret-key")
    assert (await client.get("/api/v1/auth/config")).json()["turnstile_site_key"] == "site-key"


async def test_register_login_and_reset_need_a_solved_challenge(client, turnstile_on):
    calls, answers = turnstile_on

    missing = await _sign_up(client)
    assert missing.status_code == 400
    assert not calls

    ok = await _sign_up(client, captcha_token="good-token")
    assert ok.status_code == 201, ok.text
    assert calls[0][0] == "good-token"

    credentials = {"email": "newbie@example.com", "password": PASSWORD}
    assert (await client.post("/api/v1/auth/login", json=credentials)).status_code == 400
    assert (
        await client.post("/api/v1/auth/login", json={**credentials, "captcha_token": "t"})
    ).status_code == 200

    reset = {"email": "newbie@example.com"}
    assert (await client.post("/api/v1/auth/password-reset", json=reset)).status_code == 400
    assert (
        await client.post("/api/v1/auth/password-reset", json={**reset, "captcha_token": "t"})
    ).status_code == 202

    answers["success"] = False
    failed = await client.post("/api/v1/auth/login", json={**credentials, "captcha_token": "bad"})
    assert failed.status_code == 400
    assert "CAPTCHA" in failed.json()["error"]["message"]


async def test_a_failed_challenge_never_reaches_the_password_check(client, turnstile_on):
    _, answers = turnstile_on
    await _sign_up(client, captcha_token="t")
    answers["success"] = False
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "newbie@example.com", "password": "wrong-password", "captcha_token": "x"},
    )
    assert r.status_code == 400  # not 401: the password was never checked


async def test_when_cloudflare_is_unreachable_the_request_is_refused(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "turnstile_site_key", "site-key")
    monkeypatch.setattr(settings, "turnstile_secret_key", "secret-key")

    async def down(token, remote_ip, _settings):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(captcha_module, "_siteverify", down)
    r = await _sign_up(client, captcha_token="t")
    assert r.status_code == 503


async def test_no_challenge_is_needed_when_turnstile_is_not_configured(client):
    assert (await _sign_up(client)).status_code == 201
