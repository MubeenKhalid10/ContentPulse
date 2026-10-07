"""Optional outgoing email over SMTP.

Email is a convenience, never a requirement: when SMTP is not configured, or
the server refuses a message, ``send_email`` logs it and returns False so the
caller can fall back (show the invite link, ask an admin) instead of failing.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)


def _send_sync(settings: Settings, message: EmailMessage) -> None:
    host, port, timeout = (
        settings.smtp_host or "",
        settings.smtp_port,
        settings.smtp_timeout_seconds,
    )
    if settings.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=timeout, context=ssl.create_default_context()
        )
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    with server:
        if settings.smtp_security == "starttls":
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


async def send_email(settings: Settings, *, to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True only if the SMTP server accepted it."""
    if not settings.email_enabled:
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        await asyncio.to_thread(_send_sync, settings, message)
    except (OSError, smtplib.SMTPException) as exc:
        # Never log the body: it carries a sign-in or reset link.
        logger.warning("Email to %s not sent (%s): %s", to, subject, exc.__class__.__name__)
        return False
    return True
