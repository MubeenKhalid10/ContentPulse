"""Optional SMTP email: invitations and local password reset."""

import re

import pytest

from app.core import email as email_module
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.security import create_password_reset_token, decode_local_token


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(settings, message):
        sent.append(message)

    monkeypatch.setattr(email_module, "_send_sync", fake_send)
    return sent


@pytest.fixture
def smtp_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "ContentPulse <no-reply@example.com>")
    return settings


async def _register(client, email="reset@example.com", password="original-password"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Rae Reset"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_config_reports_reset_only_with_smtp(client, smtp_on):
    r = await client.get("/api/v1/auth/config")
    assert r.json()["password_reset"] is True


async def test_config_without_smtp(client):
    r = await client.get("/api/v1/auth/config")
    assert r.json()["password_reset"] is False


async def test_reset_flow_end_to_end(client, smtp_on, outbox):
    await _register(client)
    r = await client.post("/api/v1/auth/password-reset", json={"email": "Reset@Example.com"})
    assert r.status_code == 202
    assert len(outbox) == 1
    body = outbox[0].get_body(preferencelist=("plain",)).get_content()
    token = body.split("/reset-password#token=")[1].split()[0]
    html = outbox[0].get_body(preferencelist=("html",)).get_content()
    assert "Reset password" in html and "ContentPulse" in html

    # A reset token is never a session.
    with pytest.raises(Unauthorized):
        decode_local_token(token, smtp_on)

    r = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "brand-new-password"},
    )
    assert r.status_code == 200, r.text

    # Old password is gone, new one works.
    bad = await client.post(
        "/api/v1/auth/login", json={"email": "reset@example.com", "password": "original-password"}
    )
    assert bad.status_code == 401
    good = await client.post(
        "/api/v1/auth/login", json={"email": "reset@example.com", "password": "brand-new-password"}
    )
    assert good.status_code == 200

    # The link works once.
    again = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "another-password-1"},
    )
    assert again.status_code == 401


async def test_unknown_email_gets_same_answer_and_no_mail(client, smtp_on, outbox):
    r = await client.post("/api/v1/auth/password-reset", json={"email": "nobody@example.com"})
    assert r.status_code == 202
    assert outbox == []


async def test_no_smtp_sends_nothing(client, outbox):
    await _register(client, email="quiet@example.com")
    r = await client.post("/api/v1/auth/password-reset", json={"email": "quiet@example.com"})
    assert r.status_code == 202
    assert outbox == []


async def test_expired_or_forged_token_rejected(client, smtp_on):
    user = await _register(client, email="forge@example.com")
    import uuid

    forged = create_password_reset_token(uuid.UUID(user["user"]["id"]), "not-the-hash", smtp_on)
    r = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": forged, "password": "brand-new-password"},
    )
    assert r.status_code == 401


async def test_smtp_failure_never_breaks(monkeypatch, smtp_on):
    def boom(settings, message):
        raise OSError("connection refused")

    monkeypatch.setattr(email_module, "_send_sync", boom)
    ok = await email_module.send_email(smtp_on, to="a@example.com", subject="s", body="b")
    assert ok is False


async def test_invitation_is_emailed_when_smtp_is_set(client, smtp_on, outbox):
    me = await _register(client, email="boss@example.com")
    auth = {"Authorization": f"Bearer {me['access_token']}"}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Mail Co"}, headers=auth)
    ).json()
    r = await client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "new@example.com", "role": "creator"},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is True
    assert outbox[0]["To"] == "new@example.com"
    plain = outbox[0].get_body(preferencelist=("plain",)).get_content()
    html = outbox[0].get_body(preferencelist=("html",)).get_content()
    # The link goes to the invitee only; the inviter isn't handed it.
    assert r.json()["invite_url"] is None
    link = re.search(r"https?://\S+/invite/\S+", plain).group(0)
    # The branded HTML version has the Accept button pointing at the same link.
    assert "Accept invitation" in html and f'href="{link}"' in html
    assert "Mail Co" in html and "Join Mail Co on ContentPulse" in html


async def test_invitation_without_smtp_returns_link_only(client, outbox):
    me = await _register(client, email="boss2@example.com")
    auth = {"Authorization": f"Bearer {me['access_token']}"}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Link Co"}, headers=auth)
    ).json()
    r = await client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "new2@example.com", "role": "viewer"},
        headers=auth,
    )
    assert r.json()["email_sent"] is False and r.json()["invite_url"]
    assert outbox == []


def test_invitation_email_is_branded_escaped_and_has_a_plain_fallback():
    from app.core.email_templates import invitation_email

    url = "https://example.com/invite/abc123"
    text, html = invitation_email(
        organization="Acme <script>alert(1)</script> & Co",
        role="creator",
        invite_url=url,
        expires_in_hours=72,
        inviter="Rae Admin",
        site_url="https://example.com",
    )
    assert url in text and "3 days" in text
    assert "Accept invitation" in html and f'href="{url}"' in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Rae Admin" in html and "Creator" in html
