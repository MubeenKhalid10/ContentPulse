# Going to production

ContentPulse runs locally with only Postgres. A shared, always-on deployment needs a few
more settings. Nothing here is tied to one host: AWS (see `infra/aws`), a VPS, Render,
Fly or Railway all work. Work through this list before inviting a real client.

## Must do

| Setting | Why | Value |
|---|---|---|
| `APP_ENV=production` | Turns on the production safety checks (the API refuses to start with the development JWT secret). | `production` |
| `JWT_SECRET` | Signs sessions and password-reset links. | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it out of git. |
| `FRONTEND_URL`, `CORS_ORIGINS` | Invite and reset links point to `FRONTEND_URL`; the browser may only call the API from these origins. | Your HTTPS address, e.g. `https://app.example.com` and `["https://app.example.com"]` |
| `COOKIE_SECURE` | Session cookies only over HTTPS. Empty already means "on" in production. | empty, or `true` |
| `DATABASE_URL` | A managed Postgres with backups and pgvector. | `postgresql+asyncpg://…` |
| `CRAWLER_ALLOW_PRIVATE_NETWORKS` | Must stay off: it disables the crawler's SSRF protection. | `false` |

## Should do

- **Storage.** Set `S3_BUCKET` (plus `AWS_REGION` and credentials, or `S3_ENDPOINT_URL` for
  Cloudflare R2, MinIO or Supabase Storage). Without it, uploads sit on the API server's
  disk and are lost when the server is replaced. Add the bucket CORS rule from the README.
- **Redis.** Set `REDIS_URL` when more than one API or worker process runs, so rate
  limits and AI quotas are shared (`RATE_LIMIT_BACKEND=redis`, `LLM_LIMITER_BACKEND=redis`).
- **Background jobs.** Above one server, run jobs on Celery: `TASK_BACKEND=celery`, then
  start `celery worker` and `celery beat` (beat schedules trend discovery, recovery of
  interrupted jobs and the daily clean-up).
- **Email.** Set `SMTP_HOST`, `SMTP_FROM` and the login (see `.env.example`) so
  invitations are emailed and "Forgot password" works in local sign-in mode. Use a
  sending domain with SPF and DKIM set up, or messages land in spam.
- **AI limits.** `backend/llm_limits.json` holds free-tier figures. Set your account's
  real limits there or in `LLM_LIMITS`, including the daily image cap (`rpd` for
  `kie/*` and `cloudflare/*`). Optionally cap daily requests with `LLM_ORG_DAILY_REQUEST_BUDGET` (per organization) or `LLM_DAILY_REQUEST_BUDGET` (whole app).
- **Monitoring.** `METRICS_ENABLED=true` serves Prometheus metrics at `/health/metrics`;
  keep that path off the public internet. `/health/live` is the liveness check and `/health` checks the database too.

## Rotating API keys

Rotate any key that was ever pasted into a chat, a ticket, a screenshot or a shared
`.env`, and every key on a schedule (every 90 days is a sensible default):

1. Create a new key in the provider's console (Google AI Studio, Anthropic Console,
   OpenAI, Groq, Cerebras, OpenRouter, Kie AI, Cloudflare, AWS IAM, your SMTP service).
2. Put it in the server's environment (or secret manager) and restart the API and workers.
3. Run `python -m app.ai.check` in `backend/` to confirm the text, embedding and image
   models answer.
4. Delete the old key in the provider's console.

For `JWT_SECRET`, rotating signs everyone out and voids open reset links. Do it when the
secret may have leaked.

## Data kept

- Model request history (`llm_requests`: metadata only, never prompts or outputs) is
  kept for `LLM_REQUEST_RETENTION_DAYS` (default 90) and then deleted daily.
- The audit log, posts, versions and design files are kept until an admin deletes them.

## Not included yet

Direct publishing and scheduling to LinkedIn, X, Instagram and Facebook. Each needs a
developer app approved by the platform (LinkedIn Marketing API, X API, Meta Graph API),
OAuth connection per client account, and token refresh. Today, approved posts are shared
through the device share sheet or copied.
