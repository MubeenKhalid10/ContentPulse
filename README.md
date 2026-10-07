# ContentPulse

AI-assisted content intelligence platform: discover trends, judge their relevance to an
organization, and turn the good ones into on-brand, designed, approved social posts.

> Discover → Analyze → Align → Recommend → Generate → Design → Review → Approve

This repository follows the MVP → production technical specification.

- **Sprint 1 (Foundation):** sign up, create and manage an organization, invite a team with
  role-based access; every change is audited. The full core schema (spec §72) and the
  backend-enforced post state machine (§54) are in place.
- **Sprint 2 (Organization Knowledge):** the organization's website is crawled into a
  searchable knowledge base: page extraction, heading-aware chunking, embeddings in
  pgvector, hybrid keyword + semantic retrieval, plus manually added documents.
- **Sprint 3 (Trend Engine):** ten source adapters, normalization, cross-source
  de-duplication, explainable scoring, scheduled discovery and the Trends UI. Free sources
  work with no keys; every other source can be configured later and is skipped until then.
- **Sprint 4 (AI Alignment):** every trend is judged against the organization (services,
  audience, brand) with retrieval from the knowledge base. An LLM (Gemini by default, or
  Claude) produces a relevance level, confidence, matched services, cited reasoning, content
  angles and claims to avoid. Without an LLM key, a free rule-based estimate runs instead.
- **Sprint 5 (Topic Management):** relevant trends become topic candidates that content
  managers shortlist or reject. Each topic gets explainable platform recommendations from an
  editable platform playbook. Shortlisted topics get content strategies per platform, drafted
  by AI or from the playbook, then edited and approved.
- **Sprint 6 (Content Studio):** approved strategies become platform-specific posts written
  from per-platform prompts, grounded in the knowledge base and checked against brand and
  playbook rules. Posts can be edited (every save is a new version), regenerated with
  instructions, branched into variants, restored from history and sent to the designer.
- **Sprint 7 (Design Workflow):** sending a post to design creates a design brief (built
  from the post immediately, refined by AI when configured). Designers take tasks, upload
  creatives straight to storage through signed URLs (S3 or a local fallback), every upload
  becomes a new creative version, and the finished design is submitted for approval.
- **Sprint 8 (Approval):** an approval queue where admins review each submission against
  the exact copy and creative versions submitted, with the topic, trend sources, brief and
  full history alongside. They approve (then mark final), request changes (the comment is
  pinned to the reviewed versions and the task returns to the designer or writer), or
  reject. Revisions go back as new rounds, so the whole trend-to-final workflow runs end to
  end.
- **Sprint 9 (Production readiness):** background jobs can run on Celery workers with
  Celery beat scheduling (opt-in; the default still runs everything inside the API, so
  local use needs nothing extra). AI jobs retry automatically after rate limits and outages;
  sign-in, sign-up and AI endpoints are rate limited. The repo also includes production
  images, a production-like Docker Compose profile and an optional AWS setup (Terraform for
  ECS Fargate, RDS, ElastiCache and S3) with a one-command deploy.

## Stack

| Layer    | Tech |
|----------|------|
| Frontend | Next.js 16, TypeScript, Tailwind v4, shadcn/ui, TanStack Query, React Hook Form, Zod |
| Backend  | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Data     | PostgreSQL + pgvector, Redis (Celery broker and rate-limit counters; optional locally) |
| Jobs     | In-process asyncio (default) or Celery worker + beat (`TASK_BACKEND=celery`) |
| Deploy   | Docker images; optional AWS via Terraform: ECS Fargate, RDS, ElastiCache, S3, ALB (`infra/aws`) |
| Auth     | Local email/password JWT (default) or Supabase Auth (`AUTH_PROVIDER=supabase`) |
| AI       | Google Gemini (free tier) or Claude, behind one provider interface; rule-based without a key |

## Quick start

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env                 # defaults work for local dev
docker compose up -d                 # Postgres+pgvector on :5434, Redis on :6380

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # http://localhost:8000  (docs at /docs)

cd ../frontend
npm install
npm run dev                          # http://localhost:3000
```

Open http://localhost:3000, create an account, and set up your organization. Then open
**Knowledge base** and crawl your website.

### Optional: run jobs on Celery locally

You don't need this for local use: jobs run inside the API by default. To try the
production setup, set `TASK_BACKEND=celery` in `.env`, restart the API, and run these in
two more terminals:

```bash
cd backend
uv run celery -A app.workers.celery_app worker --loglevel=info --pool=solo   # --pool=solo on Windows
uv run celery -A app.workers.celery_app beat --loglevel=info
```

Or run the whole production-like stack in containers with
`docker compose --profile app up -d --build`. Stop your dev servers first, or set
`WEB_PORT`/`API_PORT`. It runs the migrations, then the API, a Celery worker, beat and the
web app.

### Optional: deploy to AWS

See [infra/aws/README.md](infra/aws/README.md): run `terraform apply` once, then
`infra/aws/deploy.sh` for each release.

Knowledge search works out of the box with Postgres full-text search. To also match by
meaning, set `EMBEDDING_PROVIDER=openai` and `EMBEDDING_API_KEY` (any OpenAI-compatible
endpoint returning 1536-dim vectors works via `EMBEDDING_BASE_URL`), then click
**Re-index** on the knowledge page.

## Tests

```bash
cd backend && uv run pytest          # 201 tests (hermetic: ignores your .env keys)

# E2E: API + web must be running. Start the API with
#   CRAWLER_ALLOW_PRIVATE_NETWORKS=true  (knowledge spec crawls a local fixture site)
#   TREND_SCHEDULER_ENABLED=false        (trends spec runs discovery itself; needs internet)
#   AUTH_PROVIDER=local                  (the specs sign up with email/password)
#   LLM_PROVIDER=none                    (deterministic rule-based analysis, no quota use)
#   DATABASE_URL=...:5434/contentpulse_e2e  (own database: test orgs never reach dev data;
#                                         migrate it first with `alembic -x url=... upgrade head`)
cd frontend && npx playwright install chromium && npm run test:e2e   # one spec at a time; E2E_WORKERS=3 to parallelize
```

Backend tests run real migrations (down + up) against Postgres and cover auth, tenant
isolation, RBAC, invitations, the last-admin guard, audit diffs and the state machine. The
E2E test drives signup → onboarding → profile/services/brand/settings → invite → designer
accepts → read-only RBAC → activity log → sign out. The knowledge E2E crawls a fixture
site, searches it, inspects chunks, adds a manual document, excludes a page and re-crawls.
The trends E2E discovers live trends, shortlists one, then plans and approves a content
strategy for its topic and edits the platform playbook.
Knowledge tests serve a fake website through `httpx.MockTransport` and use a deterministic
fake embedder, so the real pgvector and full-text queries run without network access.

## Repository layout

```
backend/
  app/
    ai/             LLM gateway, provider adapters, quotas, metrics, embeddings (spec §57)
    api/v1/         auth, organizations (incl. team + audit), knowledge, dashboard
    core/           config, errors (spec §55 envelope), security, permissions (RBAC)
    models/         all core tables (§72) + prompt_templates
    schemas/        Pydantic request/response models
    services/       auth, organization/team, audit, workflow (state machines), dashboard
      knowledge/    urls, fetcher (SSRF-safe), crawler, extractor, chunker, indexer, search
    workers/        job dispatch (in-process or Celery), Celery app + beat, crawl/trend jobs, scheduler
    storage/        creative storage: S3 or local signed URLs
    db/migrations/  Alembic
  tests/
frontend/           see frontend/README.md
infra/postgres/     DB init (pgvector, test and E2E databases)
infra/aws/          optional AWS deployment: Terraform + deploy.sh (see its README)
docker-compose.yml  infrastructure by default; `--profile app` for the full container stack
```

## Roles and the workflow

Three roles (`backend/app/core/permissions.py`):

| Role | Can do |
|---|---|
| **Admin** | Everything: organization setup, team, discovery, **approving posts** |
| **Creator** | Shortlist topics, plan and write posts, add the design and submit for approval |
| **Viewer** | See everything and share finished posts; no changes |

One post, start to finish (about 7 clicks):

1. **Topics** → "Shortlist" a topic (or "Shortlist" on a trend: it lands in Topics).
2. Topic page → "Plan for LinkedIn" (or "New plan") → "Draft with AI" → **"Save & write post"**.
   There is no separate plan approval: writing the post approves the plan.
3. Studio → edit, "Save version" → **"Send to design"** (opens the design task).
4. Design task → drop the files → **"Upload & submit for approval"**.
5. Admin: **Approvals** → **"Approve"**. The post is now *Ready to publish* (locked); "Share"
   appears on it. "Request changes" sends it back to the creator, who fixes the copy and/or
   uploads a new design and resubmits; "Reject" ends it.

Post statuses as people see them: Draft → Needs design → In design → Design added → Waiting for
approval → Changes needed → Ready to publish. Copy stays editable during design. Older sprint notes
below mention content managers and designers: both are now the Creator role (migration
`5d8a2f4c7e91` moved existing members and posts).

## Key design decisions

- **Multi-tenancy.** Every org-owned table has `organization_id`. Every org-scoped route
  resolves an `OrgContext` proving active membership; non-members get **404, not 403**, so
  organization ids cannot be probed. Child resources are always fetched with
  `id AND organization_id`.
- **Active organization.** Routes under `/organizations/{id}` use the path. Routes without
  one (dashboard, later trends/topics) use the `X-Organization-Id` header, falling back to
  the user's first organization.
- **Sessions.** The API issues a JWT returned in the body and set as an httpOnly,
  SameSite=Lax cookie. The web app proxies `/api/v1` through Next.js so the cookie is
  first-party; API clients can use `Authorization: Bearer`.
- **Invitations.** Admins get a single-use link (only its SHA-256 hash is stored; 72h TTL).
  Accepting as an *existing* account requires that account's password: holding the link
  alone never grants a session. Email delivery comes later.
- **Guards.** An organization can never lose its last active admin (row-locked check on
  demote, disable and remove).
- **Audit log.** Writes record only the fields that actually changed (old → new); no-op
  PATCHes create no entry.
- **State machines.** Post, topic and trend statuses change only through
  `app/services/workflow.py`; invalid moves return `INVALID_STATE_TRANSITION` (409). Moving
  a post to `design_uploaded`/`pending_approval` requires an uploaded creative.
- **Enums** are stored as VARCHAR + CHECK constraints: readable in SQL, cheap to extend.
- **Embeddings** use `vector(1536)` with an HNSW cosine index. Changing embedding
  dimensionality needs a migration and re-index.

### Production readiness (Sprint 9)

- **One dispatch point for background work (rule 6, §44):** every job is a named async
  function that takes one id (`app/workers/tasks.py`). `enqueue()` runs it inside the API
  (`TASK_BACKEND=inprocess`, the default) or sends it to Celery (`celery`). Job state lives
  in Postgres either way, so the UI can't tell the difference. If the broker is unreachable,
  the job runs in-process rather than being lost.
- **Celery:** each worker process keeps one event loop and reuses the same job code.
  `acks_late` re-delivers a job if its worker dies, and jobs skip work that's already done.
  Infrastructure errors that happen before a job records anything (an unreachable
  database, for example) retry with backoff. Beat triggers due trend discovery every minute
  (the Postgres advisory lock still guarantees a single scheduler) and marks interrupted
  jobs as failed every 10 minutes. In Celery mode the API's own scheduler loop stays off.
- **AI retries (§56):** post generation, trend analysis and design briefs that hit a rate
  limit or an outage go back in the queue after `JOB_RETRY_DELAYS` (30 s, then 120 s). This
  is on top of the provider's own retries and model fallback. Permanent errors (a bad key,
  a refusal) fail at once, with the reason shown.
- **Rate limits (§61):** fixed windows stored in Redis and shared across API instances. If
  Redis is unreachable they fall back to memory rather than failing requests.

  | Limit | Window | Key |
  |-------|--------|-----|
  | Every `/api` request: 600 (`API_RATE_LIMIT_PER_MINUTE`) | 1 min | client IP |
  | Sign-in: 30 per IP, 10 per account | 15 min | IP / email |
  | Sign-up: 20 | 1 hour | IP |
  | Accepting invitations: 30 | 1 hour | IP |
  | AI and heavy jobs (generate, regenerate, variants, strategy drafts, analyze, discover): 30 | 1 min | user |

  Over a limit, the API returns `429 RATE_LIMITED` with a `Retry-After` header. Client IPs
  come from `X-Forwarded-For` only for the number of trusted proxy hops
  (`TRUSTED_PROXY_COUNT`, counted from the right), so clients can't choose their own bucket.
- **Health:** `/health/live` checks that the process is up; `/health` checks that the
  database answers (the load balancer uses it).
- **Images:** one backend image (the API by default; the worker and beat override the
  command) and a standalone Next.js image. Migrations run as their own step, never on every
  container start.

### Authentication modes

- **`AUTH_PROVIDER=local`** (default): email/password with an httpOnly session cookie.
- **`AUTH_PROVIDER=supabase`:** the web app reads `GET /auth/config` at runtime and signs in
  through Supabase Auth (`@supabase/ssr`, session in `sb-*-auth-token` cookies), so it needs
  no separate config. Each API call sends the Supabase access token as a Bearer token. The
  API verifies it against the project's JWKS (ES256/RS256, cached, refetched on key
  rotation), checking audience `authenticated` and the project issuer. The legacy HS256
  secret is also accepted. The first request provisions or links the ContentPulse user (by
  Supabase user id, then email), and the API's password endpoints return 403. To accept an
  invitation, you need a Supabase session for the invited email address.
- Email links land on `/auth/callback`, which completes the PKCE exchange and continues to
  `/onboarding`, `/auth/reset` or the invitation.

### Approvals (Sprint 8)

- **Rounds pin what was reviewed (§31, §33):** each submission creates an
  `approval_request` recording the copy version and creative version it covers. Comments
  (and the reason given with each decision) are stored with those same versions, so "reduce
  the text on slide 3" always refers to the slide it was written about, even after v3
  exists. The review page warns when the copy has changed since the submission.
- **Decisions (§32, §42, admins only):**
  - **Approve:** the post moves to `approved` and the design task completes. "Mark as
    final" then moves it to `final`.
  - **Request changes:** needs a comment, and says who acts:
    - design: the task returns to the designer's to-do list, same assignee, with the
      feedback shown;
    - copy: the writer revises in the studio and resubmits with the current creative;
    - or both.
  - **Reject:** ends the workflow and closes the task.
  
  Each submission can be decided once; a second decision returns `409`.
- **Resubmission:** from the design task after a new upload, or from the studio after
  copy-only changes. Either way it opens a new round, and earlier rounds, comments and
  versions all stay visible.
- **Who sees what:** admins review. Content managers can read the queue and comment.
  Designers get the feedback on their task rather than the queue (per §6 they have no
  `approval.read`). Every decision and comment is in the audit log.

### Design workflow (Sprint 7)

- **Briefs (§27-28):** "Send to designer" moves the post to `design_pending` and creates
  its design brief, which is also the designer's task. The brief is built straight from the
  post, so the task is usable at once:
  - format and platform-specific dimensions;
  - the hook as the headline and the opening sentences as supporting text;
  - slides parsed from the visual concept, or the spec's six-slide carousel outline;
  - the CTA;
  - brand requirements (colors, typography, logo, terms to avoid), always read from the
    database, never from the model.

  With an LLM configured, `design_brief.txt` then rewrites the creative direction in the
  background, unless someone has already edited the brief. Moving the post back to draft
  cancels the task; sending it again opens a new one for the same designer.
- **Tasks (§30, §41, §52):** admins assign tasks to designers, and designers can take
  unassigned ones (uploading also claims the task). Only the assignee (or a design manager)
  can deliver. Content managers own the brief's wording; designers deliver the files.
- **Uploads, never through the API in production (§41, §61):**
  `POST /design/tasks/{id}/uploads` returns a short-lived signed URL. The browser PUTs the
  file directly to storage, then `POST /design/tasks/{id}/assets` registers it. The API
  checks that each object really exists under that task's key prefix, re-checks the size and
  type, and records the files as the next creative version. Files are never replaced, and
  are viewed and downloaded through short-lived signed URLs only.
- **Storage adapters:** `S3Storage` uses presigned URLs, and works with S3-compatible
  stores via `S3_ENDPOINT_URL`. `LocalStorage` is the zero-config fallback: JWT-signed upload
  and download URLs served by the API, with the type and size cap enforced while streaming.
  For S3, allow the browser in the bucket's CORS configuration:

  ```json
  [{"AllowedOrigins": ["https://your-app.example.com"],
    "AllowedMethods": ["PUT", "GET"], "AllowedHeaders": ["Content-Type"], "MaxAgeSeconds": 3000}]
  ```
- **Submission:** `design_uploaded → pending_approval`. The state machine refuses it without
  an uploaded creative (§54). Sprint 8 handles approval and change requests.

### Content studio (Sprint 6)

- **Generation (§23, §26):** an approved strategy becomes a post, written in the background
  by `app/services/content/generation.py`. The prompt combines the platform's own template
  (`linkedin_post.txt`, `x_post.txt`, `instagram_post.txt`, `facebook_post.txt`,
  `blog_post.txt`), the
  organization profile, the platform playbook, the strategy, the topic analysis (including
  claims to avoid), recent coverage, brand vocabulary and up to 6 knowledge passages.
  Output is JSON-schema structured: hook, body, CTA, hashtags, visual concept, design format
  and cited passages. The frontend never parses prose.
- **Validated in code:** hashtags are normalized, de-duplicated and capped at the playbook
  limit; citations to passages that weren't provided are dropped; every version (AI or
  human) is checked for forbidden brand terms, the platform length limit, the hashtag limit
  and a missing CTA, and the warnings are shown next to the editor.
- **Blog (long-form articles):** a fifth platform with the same workflow (strategy →
  generation → versions → design → approval → final), its own playbook (no hashtags,
  20,000-character limit), strategist prompt (`blog_strategy.txt`) and writer prompt
  (`blog_post.txt`). Blog strategies carry an SEO plan in `content_strategies.details`
  (working title, primary/secondary keywords, search intent, outline, target length,
  featured-image direction). A blog version reuses the post fields (`hook` = introduction,
  `body` = Markdown with `##` sections and a conclusion, `cta`) and keeps its SEO title,
  meta title/description, slug and keywords in `metadata.blog`; extra checks flag short
  articles, missing headings, over-long meta fields and a primary keyword missing from the
  title/introduction. The design task is the featured image (1200×630). Blog is never
  published automatically: final articles are copied or downloaded as Markdown for the CMS.
  Logic lives in `app/services/content/blog.py`.
- **Versions, never overwrites (rule 4):** saving, regenerating (optionally with editor
  instructions) and restoring all add a version, so earlier ones are never changed. Edits
  carry `base_version`, and a save based on an older version is rejected with 409 instead
  of silently overwriting a colleague's work.
- **Variants:** "Create variant" writes a separate post from the same strategy, prompted to
  differ from the existing one. Variants are grouped so the team can compare them.
- **Failure (§56):** provider retries and model fallback happen inside the provider. If the
  call still fails, the job is marked FAILED with the reason, existing versions are
  untouched, and the studio shows "Try again". With no AI configured, a clearly labeled
  template draft built from the strategy is created instead.
- **Workflow (§25):** draft ⇄ in review → sent to design (or archived), enforced by
  `POST_MACHINE`. Copy is editable only while drafting. Sprint 7 picks up from
  `design_pending` with design briefs.

### Topics and strategies (Sprint 5)

- **Topic candidates (§19-20):** created automatically when alignment rates a trend relevant
  or highly relevant, when someone overrides it to one of those levels, or when the trend is
  shortlisted. Re-analysis refreshes the analysis fields (relevance, services, angles, claims
  to avoid, platforms) but never the title, summary, audience or status a person set.
  Shortlisting, rejecting and restoring are mirrored between a topic and its trend, so the
  Trends and Topics pages always agree. Topics that existed as trends before this sprint are
  backfilled at startup.
- **Platform playbook (§22):** post types, objectives, audience signals, tone, length,
  hashtag limits and guidance per platform live in `platform_rules`, one row per organization
  and platform, seeded from `app/services/topics/platform_defaults.py`. Admins edit them on
  Organization > Platform playbook. Nothing about platforms is hardcoded in prompts.
- **Platform recommendation:** a deterministic score per enabled platform, built from a
  base score, AI angles targeting that platform, playbook keywords that match the
  organization's audience and goals or the topic, and where the trend is already being
  discussed. Every point comes with a reason, and platforms scoring 50 or more are
  recommended (at least one always is).
- **Content strategies (§21):** only shortlisted topics get strategies. Post types must come
  from the platform's playbook (normalized to its spelling), and the platform must be one
  the organization uses. "Draft with AI" uses the versioned `content_strategy` prompt with a
  JSON schema whose post-type and objective enums come from the playbook. Every call is
  recorded in `ai_generation_jobs`. If the AI fails or isn't configured, a rule-based draft
  built from the playbook, the topic analysis and the brand comes back instead, with a note
  explaining why, so the button always works. Strategies move draft → approved
  (`STRATEGY_MACHINE`). Approved strategies must be reopened before editing, and archived ones
  are kept for reference.

### AI alignment (Sprint 4)

- **Flow (§14-17):** discovery finishes, then an alignment job takes the top trends by
  opportunity. For each trend it retrieves up to 6 knowledge passages (hybrid search on topic
  and keywords), builds the org profile (services, audience, markets, goals, brand), and gets
  a structured result. Results are stored on the trend, `organization_fit` and
  `audience_relevance` join the scoring signals, the opportunity score is recomputed, and the
  trend moves to `analyzed`.
- **Gemini (`GeminiProvider`, default):** the REST `generateContent` API with
  `responseJsonSchema` structured output. Through the LLM gateway (below), 429s and 503s
  are retried with backoff, then `gemini-3.5-flash` takes over from `gemini-3.8-flash`.
  Safety blocks surface as refusals. A retired or mistyped `LLM_MODEL` falls back to the
  current default instead of failing every analysis.
- **Claude (`AnthropicProvider`, official SDK):** `claude-opus-5-5` at configurable effort,
  with JSON-schema structured output (`output_config.format`) so nothing parses free prose
  (§26). The org profile sits in a cached system prompt. Refusals are handled
  (`stop_reason`), with server-side `fallbacks: "default"`; on outages the gateway retries
  and then `LLM_FALLBACK_MODEL` is tried (§56).
- **Grounding enforced in code (§71 rules 1-2):** services the model names that aren't in
  the org's list are removed. Citations to passages that weren't provided are removed. Angles
  for weak or irrelevant trends are dropped. Scores are clamped. Every correction is
  recorded on the job.
- **Traceability (§56, §59):** prompts live in `app/ai/prompts/*.txt` with explicit
  versions, registered in `prompt_templates`. Every analysis writes an `ai_generation_jobs`
  row with provider, model, prompt version, tokens, status and error, so you can always
  answer "which prompt generated this?"
- **No key, no problem:** the rule-based engine classifies from service mentions,
  knowledge passages about the topic, and tracked-keyword matches. Its confidence is lower,
  it writes no angles, and it is labeled as an estimate. Once an LLM is configured, earlier
  estimates are re-analyzed by AI on the next run.
- **Humans decide (§16):** content managers can override the relevance level (the analysis
  stays recorded, and re-analysis never overwrites a human decision), re-run analysis, or
  retry a failed one. `GET /ai/status` tells the UI which engine is active.
- **Cost guard:** AI analyzes at most `ALIGNMENT_AI_BATCH_SIZE` trends per run.

### LLM gateway (quotas, retries, fallback)

Every model call (trend analysis, strategy drafts, posts, design briefs, embeddings)
goes through `app/ai/gateway.py`. Full guide: [docs/llm-gateway.md](docs/llm-gateway.md).

- **Quotas, not just retries:** before sending, a call reserves RPM, TPM, requests/day,
  tokens/day and a concurrency slot for its model, plus any application budgets. Each is
  checked independently, at 80% of the published limit (`LLM_RATE_LIMIT_SAFETY_FACTOR`).
  Limits come from `backend/llm_limits.json` (+ `LLM_LIMITS`).
- **Shared by every process:** with Redis reachable, one Lua script checks and reserves
  everything atomically, so the API and Celery workers can't add up past a limit. Without
  Redis (the default local setup, one process) counters live in memory.
- **Queue, then retry, then fall back:** a call without room waits in line (20s
  interactive, 10 min background) instead of failing. 429/5xx are retried with backoff,
  honoring Retry-After. A rate limit, outage, retired model or spent daily quota moves to
  the next model (`LLM_FALLBACK_MODEL`, `LLM_FALLBACKS`, or per-workflow `LLM_ROUTES`,
  across Gemini, Anthropic, OpenAI, Groq, Cerebras and OpenRouter). A bad key or bad
  request never falls back.
- **Observable:** every request is a row in `llm_requests` (tokens, retries, fallback,
  queue wait, latency; no prompt content). `GET /api/v1/ai/usage` summarizes it per
  organization, or per job. Prometheus metrics are at `/health/metrics` with
  `METRICS_ENABLED=true`.
- **Cache:** identical trend analyses (same trend, passages, profile, prompt version and
  model) are reused per organization, never across organizations.
- **People see neutral messages** ("The AI service is temporarily busy…"), never
  provider errors.

### Trend engine (Sprint 3)

| Source | Without keys | Keys (all optional) |
|--------|--------------|---------------------|
| Google Trends | ✅ "Trending now" RSS per market | — |
| Google News | ✅ Top stories + keyword search RSS | — |
| Hacker News | ✅ Algolia API (front page + keywords) | — |
| RSS feeds | ✅ Feeds listed in Settings | — |
| Reddit | ⚠️ Public RSS (no scores, rate-limited) | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |
| NewsAPI | Needs setup | `NEWS_API_KEY` |
| GNews | Needs setup | `GNEWS_API_KEY` |
| X | Needs setup | `X_BEARER_TOKEN` or `X_API_KEY` + `X_API_SECRET` |
| Instagram | Needs setup | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID` |
| LinkedIn | Unavailable: no public trends API | — |

- **Nothing optional can break discovery.** Each source reports its configuration without
  making requests. Sources with no keys are skipped and shown as "Needs setup". Every
  configured source runs concurrently inside its own boundary (timeout, typed errors,
  even an unexpected adapter bug), and its outcome is recorded per run and in its
  health: `healthy`, `rate_limited`, `degraded` or `down`. A run fails only if every
  attempted source fails.
- **Normalization (§11)** maps every source to one item model (topic, title, keywords,
  location, URL, author, published time, engagement plus a human label, raw payload).
  Free-text target markets ("USA", "United Kingdom") resolve to geo codes; unknown markets
  become run warnings.
- **De-duplication (§12)** clusters items by phrases shared across items: entities,
  acronyms, product names and recurring bigrams. Headlines Written In Title Case don't
  count as entities. Tracked keywords inform relevance, but never become a "keyword
  bucket" topic unless they appear as an entity. Clusters merge with similar ones and
  with the org's existing trends. Re-observed items update engagement, which yields a
  real growth rate.
- **Scoring (§13)** is a weighted mean of explainable 0–100 signals, each with a
  plain-language reason: popularity, growth, freshness, location relevance, source
  diversity and keyword match. Organization fit and audience relevance arrive with AI
  alignment (Sprint 4). Active trends are re-scored every run, so freshness decays.
- **Scheduling (§45/46).** Each org's frequency is hourly, every 6 hours or daily at
  08:00 in the org's timezone; new orgs get a first run within a minute. A Postgres
  advisory lock ensures only one instance schedules.
- **Shared request cache.** Identical provider requests within 10 minutes (e.g. every
  org's US Google Trends feed at 08:00) share one response. Failures are remembered for
  2 minutes, so a rate-limited provider isn't hammered.
- **Review.** Content managers can shortlist, reject or restore trends (spec §20); only
  admins run discovery or change sources.

### Knowledge base (Sprint 2)

- **Crawling** starts from robots.txt sitemaps plus the homepage, follows in-site links,
  and fetches shallow URLs first within a page budget (default 50, max 300). It respects
  robots.txt, `Crawl-delay` and `noindex`, skips assets, logins and carts, drops query
  strings, and de-duplicates by canonical URL and content hash.
- **SSRF protection.** The server fetches user-supplied URLs, so every request and every
  redirect hop must resolve to public addresses only. Localhost, private ranges and cloud
  metadata (169.254.169.254) are refused. Pages are capped at 3 MB.
- **Extraction** keeps `<main>`/`<article>` content as lightweight markdown with headings.
  It strips nav, footers, cookie banners, forms and scripts, and records title,
  description, language and headings for citations (spec §9).
- **Chunking** follows headings (~250 words, sentence-aligned splits with overlap). Every
  chunk carries its section path ("Services › AI Solutions") and is embedded with its page
  and section names. Tiny neighbouring sections are merged, keeping each sub-heading
  inline.
- **Retrieval** fuses Postgres full-text ranking (headings weighted above body; chunks
  matching every term first) with pgvector cosine search using Reciprocal Rank Fusion.
  Semantic matches under a similarity floor are dropped. Iterative HNSW scans keep the
  per-organization filter from starving results.
- **Background jobs.** Crawls and re-indexes run off the request path (spec rule 6) with
  progress, cancellation and a heartbeat. Jobs whose worker died are marked failed on
  startup. Only one job runs per organization. Re-crawls skip unchanged pages, and pages
  that now 404 lose their chunks.
- **Graceful degradation.** If the embedding provider fails mid-crawl, the crawl finishes
  with keyword-only indexing and a warning, and a later re-index adds the embeddings.

### Interpretations of the spec

- Spec role lists omit some reads that the workflow needs. Content managers also get
  `content.read` and `approval.read`; designers get `organization.read` (to see brand
  guidelines). Viewers get every `*.read`.
- `organization_services` has a `kind` (service / product / expertise) to cover the
  spec's "Services, Products, Expertise" without three tables.
- Trends are organization-scoped (each org tracks its own markets and keywords).
- Post statuses add `final` after `approved`, per the §54 state machine.

## Going to production

To deploy on Vercel (web app) + Render (API) + Supabase (database and files), follow
[docs/deploy-vercel.md](docs/deploy-vercel.md). See [docs/production.md](docs/production.md) for the checklist: secrets, HTTPS cookies,
Redis, Celery, S3, email, AI limits and key rotation.

## Roadmap

| Sprint | Scope | Status |
|--------|-------|--------|
| 1 | Foundation: auth, RBAC, organizations, team, audit, core schema | Done |
| 2 | Website crawler, extraction, chunking, embeddings, knowledge UI | Done |
| 3 | Trend sources (Google Trends, Reddit, News), normalization, dedup | Done |
| 4 | RAG retrieval + organization alignment | Done |
| 5 | Topic candidates, shortlisting, content strategies | Done |
| 6 | Content studio: LLM provider, prompts, versions | Done |
| 7 | Design briefs, S3 uploads, creative versions | Done |
| 8 | Approvals, comments, request changes | Done |
| 9 | Celery, scheduling, retries, rate limits, AWS deployment | Done |

Known gaps and limitations:

- Email (invitations, password reset) needs SMTP settings; without them admins share
  the invite link and password reset is unavailable in local sign-in mode.
- Posts aren't published to social platforms directly: "Ready to publish" posts are
  shared or copied by hand. Direct publishing needs a developer app (and review) per
  platform: LinkedIn Marketing API, X API, Meta Graph API for Instagram and Facebook.
- With the default `TASK_BACKEND=inprocess`, jobs run inside the API process. That's
  right for local use and a single server; use Celery (`TASK_BACKEND=celery`) beyond that.
- Locally, requests reach the API through the Next.js rewrite, which doesn't add the
  client's address. Per-IP limits therefore treat all local traffic as one client;
  per-account sign-in limits still apply individually. Behind the AWS load balancer they
  see real IPs.
- JavaScript-rendered sites (content only after client-side rendering) aren't supported
  yet. A Playwright rendering fallback is a planned addition.
- SSRF checks resolve DNS before connecting. A DNS-rebinding attacker could still race
  that check, so production should also route crawler egress through a proxy that blocks
  private ranges.
- Full-text search uses the English text configuration.
- Topic extraction is heuristic, so broad topics like "AI" can surface; alignment judges
  whether they matter to the organization.
- The Claude path is covered by tests with a fake client (exact request shape, refusals,
  fallback, grounding), but hasn't run against the live API in this environment because no
  key was configured. The Gemini path was verified live.
- Reddit without credentials relies on public RSS, which Reddit rate-limits heavily.
- Supabase mode covers email/password sign-up (with email confirmation), sign-in, password
  reset and invitations. OAuth providers (Google, etc.) aren't wired into the UI yet. The E2E
  suite runs in local mode. Supabase token verification is covered by backend tests
  (ES256 JWKS, key rotation, legacy HS256, invite identity checks).
