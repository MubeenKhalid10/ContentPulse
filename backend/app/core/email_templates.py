# ruff: noqa: E501  (HTML email: long inline-style lines are normal)
"""Branded HTML emails. Inline styles only (email clients ignore stylesheets),
laid out like the sign-up confirmation email so both look like one product."""

from html import escape

ROLE_BLURB = {
    "admin": "set up the organization, invite the team and approve posts",
    "creator": "choose topics, plan and write posts, and add designs",
    "viewer": "read everything and share finished posts",
}


def invitation_email(
    *,
    organization: str,
    role: str,
    invite_url: str,
    expires_in_hours: int,
    inviter: str | None,
    site_url: str,
) -> tuple[str, str]:
    """(plain text, HTML) for an invitation to join an organization."""
    role_name = role.capitalize()
    blurb = ROLE_BLURB.get(role, "work in this organization")
    who = inviter or "Someone on your team"
    days = expires_in_hours // 24
    valid = (
        f"{days} day{'s' if days != 1 else ''}"
        if expires_in_hours % 24 == 0 and days
        else (f"{expires_in_hours} hours")
    )

    text = (
        f"{who} invited you to join {organization} on ContentPulse "
        f"as {role_name} (you will {blurb}).\n\n"
        f"Accept the invitation here (the link works for {valid}):\n\n"
        f"{invite_url}\n\n"
        "Use the email address this message was sent to when you sign in or create your account.\n"
        "If you weren't expecting this, you can ignore this email.\n"
    )

    org, who_h, role_h, blurb_h = (
        escape(organization),
        escape(who),
        escape(role_name),
        escape(blurb),
    )
    url = escape(invite_url, quote=True)
    site = escape(site_url, quote=True)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>You're invited to {org} | ContentPulse</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f7fb; font-family:Arial,Helvetica,sans-serif; color:#172033;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f7fb; padding:40px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px; background-color:#ffffff; border-radius:16px; overflow:hidden;">
          <tr>
            <td align="center" style="padding:32px 24px; background-color:#111827;">
              <div style="font-size:28px; font-weight:700; letter-spacing:-1px; color:#ffffff;">Content<span style="color:#60a5fa;">Pulse</span></div>
              <p style="margin:10px 0 0; color:#cbd5e1; font-size:13px; line-height:20px;">Content intelligence. Smarter decisions.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:40px 32px 24px;">
              <p style="margin:0 0 12px; color:#2563eb; font-size:12px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase;">You're invited</p>
              <h1 style="margin:0 0 18px; font-size:28px; line-height:36px; font-weight:700; color:#111827;">Join {org} on ContentPulse</h1>
              <p style="margin:0 0 16px; font-size:15px; line-height:26px; color:#4b5563;">
                <strong style="color:#111827;">{who_h}</strong> invited you to join
                <strong style="color:#111827;">{org}</strong> as <strong style="color:#111827;">{role_h}</strong>.
              </p>
              <p style="margin:0 0 28px; font-size:15px; line-height:26px; color:#4b5563;">
                As {role_h} you can {blurb_h}.
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" align="center">
                <tr>
                  <td align="center" bgcolor="#2563eb" style="border-radius:8px;">
                    <a href="{url}" target="_blank" style="display:inline-block; padding:15px 30px; font-size:15px; line-height:20px; font-weight:700; color:#ffffff; text-decoration:none; border-radius:8px;">Accept invitation</a>
                  </td>
                </tr>
              </table>
              <p style="margin:28px 0 10px; font-size:13px; line-height:22px; color:#6b7280;">If the button doesn't work, copy and paste this link into your browser:</p>
              <p style="margin:0 0 24px; font-size:12px; line-height:20px; word-break:break-all;">
                <a href="{url}" style="color:#2563eb; text-decoration:underline;">{url}</a>
              </p>
              <div style="height:1px; background-color:#e5e7eb;"></div>
              <p style="margin:22px 0 0; font-size:13px; line-height:22px; color:#6b7280;">
                This invitation is for the email address it was sent to, so use that address when you sign in or create
                your account. The link works for {escape(valid)}. If you weren't expecting this, you can safely ignore this email.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:24px 24px 30px; background-color:#f9fafb;">
              <p style="margin:0 0 8px; font-size:13px; color:#374151; font-weight:700;">The ContentPulse Team</p>
              <p style="margin:0 0 12px; font-size:12px; line-height:20px; color:#9ca3af;">Helping you turn trends into content opportunities.</p>
              <a href="{site}" style="font-size:12px; color:#2563eb; text-decoration:none;">Visit ContentPulse</a>
            </td>
          </tr>
        </table>
        <p style="max-width:520px; margin:20px auto 0; text-align:center; font-size:11px; line-height:18px; color:#9ca3af;">
          This is an automated invitation email. Please do not reply directly.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return text, html
