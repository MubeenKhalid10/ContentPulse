"""Local sign-in: a reset link confirms the address; the database certificate is verified."""

import ssl

import certifi
import pytest

from app.core import email as email_module
from app.core.config import Settings, get_settings
from app.db.url import async_database_url

PASSWORD = "original-password"


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(email_module, "_send_sync", lambda settings, message: sent.append(message))
    return sent


@pytest.fixture
def verification_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "ContentPulse <no-reply@example.com>")
    monkeypatch.setattr(settings, "require_email_verification", True)
    return settings


def _reset_token(message) -> str:
    body = message.get_body(preferencelist=("plain",)).get_content()
    return body.split("/reset-password#token=")[1].split()[0]


async def test_password_reset_also_confirms_the_address(client, verification_on, outbox):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "forgot@example.com", "password": PASSWORD, "full_name": "Fay Forgot"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email_verified"] is False
    assert len(outbox) == 1  # the confirmation email, which she never opens

    asked = await client.post("/api/v1/auth/password-reset", json={"email": "forgot@example.com"})
    assert asked.status_code == 202
    assert len(outbox) == 2

    client.cookies.clear()
    done = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": _reset_token(outbox[1]), "password": "a-brand-new-password"},
    )
    assert done.status_code == 200, done.text
    # The reset link reached her inbox, so the address is proven.
    assert done.json()["user"]["email_verified"] is True

    # The old password is gone, the new one works, and the link can't be reused.
    client.cookies.clear()
    old = await client.post(
        "/api/v1/auth/login", json={"email": "forgot@example.com", "password": PASSWORD}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "forgot@example.com", "password": "a-brand-new-password"},
    )
    assert new.status_code == 200
    reused = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": _reset_token(outbox[1]), "password": "yet-another-password"},
    )
    assert reused.status_code == 401


def _settings(**extra) -> Settings:
    return Settings(
        _env_file=None,
        db_host="mydb.abc.us-east-1.rds.amazonaws.com",
        db_password="p@ss/word",
        **extra,
    )


def test_database_certificate_is_verified_when_a_bundle_is_configured():
    url = _settings(db_ssl_root_cert=certifi.where()).database_url
    assert "sslmode=verify-full" in url and "sslrootcert=" in url

    clean, args = async_database_url(url)
    context = args["ssl"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert "sslmode" not in clean and "sslrootcert" not in clean


def test_without_a_bundle_the_connection_is_encrypted_but_unverified():
    url = _settings().database_url
    assert "sslmode" not in url
    _, args = async_database_url(url)
    assert args["ssl"].verify_mode == ssl.CERT_NONE
