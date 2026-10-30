# Email templates (Supabase Auth)

`confirm-signup.html` is the **Confirm signup** email. Paste it in the Supabase
dashboard under *Authentication → Emails → Confirm signup*.

For the confirmation button to land on the app's "Your email is confirmed" page
(`/auth/confirmed`), set under *Authentication → URL Configuration*:

- **Site URL:** `https://contentpulse-hms.vercel.app`
- **Redirect URLs:** add
  - `https://contentpulse-hms.vercel.app/auth/confirmed`
  - `https://contentpulse-hms.vercel.app/auth/callback` (password reset)
  - `http://localhost:3000/**` (local development)

The app sets the redirect itself when someone signs up
(`emailRedirectTo`, see `frontend/src/lib/auth.ts`), so the link always returns
to the site the person signed up on. If the address is missing from the
Redirect URLs list, Supabase falls back to the Site URL instead.

## Invitation email (sent by the backend)

Team invitations are sent by ContentPulse itself over SMTP (`SMTP_HOST`,
`SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`), not by Supabase.
The message has a plain-text part and a branded HTML part with an
**Accept invitation** button; the HTML is built in
`backend/app/core/email_templates.py`. `invitation-preview.html` is a rendered
sample you can open in a browser.

Local password-reset messages use the same SMTP settings and include both a
plain-text fallback and a branded HTML **Reset password** button. In production,
use a sending domain with SPF and DKIM configured, and check the provider's
delivery or spam logs if a message is accepted by SMTP but does not appear in
the inbox.
