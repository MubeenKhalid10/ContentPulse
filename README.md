# ContentPulse

AI-assisted content intelligence for marketing teams: find the trends that matter to your
organization, and turn the good ones into on-brand, designed and approved social posts.

> Discover → Analyze → Align → Recommend → Generate → Design → Review → Approve

## What it does

- **Knows your organization.** Crawls your website into a searchable knowledge base, and
  accepts manually added documents.
- **Finds trends.** Collects them from free and optional paid sources on a schedule, removes
  duplicates and scores them.
- **Judges relevance.** Rates each trend against your services, audience and brand with an
  AI model (Gemini or Claude), or a free rule-based estimate when no key is set.
- **Plans and writes posts.** Turns a trend into a topic, a content strategy per platform
  (LinkedIn, X, Instagram, Facebook, blog) and a post, with every edit saved as a version.
- **Handles design and approval.** Creates a design brief, takes the designer's uploads,
  and lets an admin approve, request changes or reject the exact copy and creative shown.
- **Runs for a team.** Organizations, roles, invitations, an activity log and sharing of
  finished posts.

## Stack

| Layer    | Tech |
|----------|------|
| Frontend | Next.js 16, TypeScript, Tailwind v4, shadcn/ui, TanStack Query |
| Backend  | Python 3.12+, FastAPI, SQLAlchemy 2 (async), Alembic |
| Data     | PostgreSQL + pgvector; Redis (optional locally) |
| Jobs     | In-process by default, or Celery worker + beat |
| Auth     | Local email/password (default) or Supabase Auth |
| AI       | Google Gemini or Claude; rule-based without a key |
| Deploy   | Docker images; optional AWS setup with Terraform (`infra/aws`) |

## Quick start

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 22.

```bash
cp .env.example .env                 # defaults work for local dev
docker compose up -d                 # Postgres+pgvector on :5434, Redis on :6380

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # http://localhost:8000  (API docs at /docs)

cd ../frontend
npm install
npm run dev                          # http://localhost:3000
```

Open http://localhost:3000, create an account and set up your organization. Then open
**Knowledge base** and crawl your website.

## Configuration

Everything is configured through `.env` (see `.env.example` for every setting).

- **AI:** set an LLM key to get AI analysis and writing. Without one, a rule-based
  estimate and templates are used.
- **Search by meaning (optional):** set `EMBEDDING_PROVIDER=openai` and `EMBEDDING_API_KEY`
  (any OpenAI-compatible endpoint returning 1536-dimension vectors works through
  `EMBEDDING_BASE_URL`), then click **Re-index** on the knowledge page. Search works
  without it, using Postgres full-text search.
- **Sign-in:** `AUTH_PROVIDER=local` (default) or `supabase`.
- **Email:** invitations and password reset need SMTP settings. Without them, admins share
  the invite link by hand and local password reset is unavailable.
- **Trend sources:** free sources work without keys; add keys for the others in `.env`.

## Roles and the workflow

Three roles:

| Role | Can do |
|---|---|
| **Admin** | Everything: organization setup, team, discovery, **approving posts** |
| **Creator** | Shortlist topics, plan and write posts, add the design and submit for approval |
| **Viewer** | See everything and share finished posts; no changes |

One post, start to finish (about 7 clicks):

1. **Topics** → "Shortlist" a topic (or "Shortlist" on a trend: it lands in Topics).
2. Topic page → "Plan for LinkedIn" (or "New plan") → "Draft with AI" → **"Save & write post"**.
3. Studio → edit, "Save version" → **"Send to design"** (opens the design task).
4. Design task → drop the files → **"Upload & submit for approval"**.
5. Admin: **Approvals** → **"Approve"**. The post is now *Ready to publish* (locked); "Share"
   appears on it. "Request changes" sends it back to the creator, who fixes the copy and/or
   uploads a new design and resubmits; "Reject" ends it.

Post statuses as people see them: Draft → Needs design → In design → Design added → Waiting
for approval → Changes needed → Ready to publish.

## Deploying

- **Vercel + Render + Supabase:** [docs/deploy-vercel.md](docs/deploy-vercel.md)
- **AWS (Terraform):** [infra/aws/README.md](infra/aws/README.md)
- **Checklist for any production setup** (secrets, HTTPS cookies, Redis, Celery, S3, email,
  AI limits): [docs/production.md](docs/production.md)

To run background jobs on Celery locally instead of inside the API, set `TASK_BACKEND=celery`
and run a worker and beat (`uv run celery -A app.workers.celery_app worker --pool=solo`, and
`... beat`), or run the whole container stack with `docker compose --profile app up -d --build`.

## Tests and CI

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run build
```

The backend tests need the Docker Postgres from the quick start; they reset a throwaway
`*_test` database. GitHub Actions (`.github/workflows/ci.yml`) runs the same checks, plus a
Terraform format and validate check, on every pull request and push to `main`. Browser
(Playwright) tests are run by hand: see [docs/architecture.md](docs/architecture.md#testing).

## More documentation

- [docs/architecture.md](docs/architecture.md): how it is built, repository layout, design decisions
- [docs/llm-gateway.md](docs/llm-gateway.md): AI quotas, retries and fallback
- [docs/provider-cache.md](docs/provider-cache.md): trend-source caching and request budgets
- [CONTRIBUTING.md](CONTRIBUTING.md): branches, commits and pull requests

## Known limitations

- Posts are not published to social platforms automatically: "Ready to publish" posts are
  shared or copied by hand. Direct publishing needs a developer app (and review) per platform.
- Websites that only render content with JavaScript are not crawled yet.
- Reddit without credentials relies on public RSS, which Reddit rate-limits heavily.
- Supabase mode covers email/password sign-up, sign-in, password reset and invitations.
  OAuth providers (Google, etc.) are not wired into the UI yet.
- Full-text search uses the English text configuration.
- Per-IP rate limits treat all local traffic as one client; behind the AWS load balancer
  they see real client addresses.

More in [docs/architecture.md](docs/architecture.md#roadmap).
