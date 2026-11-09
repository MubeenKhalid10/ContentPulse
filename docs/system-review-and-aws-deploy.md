# ContentPulse: system review and AWS deployment guide

Written 2026-11-09 on branch `chore/hardening-and-cleanup` (after the viewer role was removed).

**How this was produced.** A code read of the auth, permission, session, rate-limit, storage,
crawler (SSRF), database, Docker, CI and Terraform files, plus a scripted check that every API
route has a guard. It is **not** a penetration test: nothing was run against a live
deployment, `.env` was never read, and the ~100 service modules were not each audited line by
line. Treat the findings as a strong start, not a certificate.

---

## Status of the findings (updated 2026-11-10)

| Finding | Status |
|---|---|
| F1 settings Terraform couldn't pass | **Fixed** (`secrets.tf` lists them; set them in the app secret) |
| F2 presigned S3 checksum | **Fixed** in code; still do one real upload on staging |
| F4 open registration | **Mitigated in code**: email confirmation (on when SMTP is set) and optional Cloudflare Turnstile for local sign-in. Supabase mode is unchanged. Also set per-org AI budgets. |
| F6 viewer migration | **Tested** on a scratch database seeded with a viewer (becomes a disabled creator; downgrade does not restore viewers). `deploy.sh` now takes an RDS snapshot before every migration. |
| F7 build context | **Fixed** (`.dockerignore`) |
| F3, F5, F8-F15 | Open |

Setting up the new sign-up protection on AWS: put `SMTP_*` (Amazon SES SMTP works) and, for the
CAPTCHA, `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY` in the app secret (section 8.7), then run
`deploy.sh`. `REQUIRE_EMAIL_VERIFICATION` can stay empty: it turns on by itself once SMTP is set.

---

## 1. What the product is

ContentPulse is a multi-tenant app that turns trends into approved social posts:

```
discover trends -> AI judges fit for the organization -> topic shortlisted
  -> content strategy per platform -> AI drafts the post -> creator edits (versioned)
  -> design brief + creative upload -> admin approves -> final
```

Platforms: LinkedIn, X, Instagram, Facebook and Blog. Nothing is posted automatically; final
posts are copied or shared by hand.

## 2. Architecture

| Layer | Technology | Notes |
|---|---|---|
| Web | Next.js (standalone Docker image) | Port 3000. Proxies `/api/v1/*` to the API (docker compose / Vercel). On AWS the load balancer sends `/api/*` straight to the API. |
| API | FastAPI + SQLAlchemy (async) + Alembic | Port 8000. One uvicorn process per task. |
| Jobs | Celery worker + Celery beat (`TASK_BACKEND=celery`) or in-process asyncio | Beat must run exactly once. |
| Database | PostgreSQL 17 + pgvector | `vector(1536)` embeddings, HNSW index. Roles are VARCHAR + CHECK. |
| Cache / limits | Redis | Celery broker, rate-limit counters, shared LLM quota. Falls back to memory if unreachable. |
| Files | S3 (presigned PUT/GET) or local disk | Browsers upload directly to S3. |
| AI | Gateway over Gemini / Claude / OpenAI / Groq / Cerebras / OpenRouter | Quotas, retries, fallback chain; every call logged (no prompt text). |
| Trend sources | Google Trends/News, Hacker News, RSS, Reddit, NewsAPI, GNews, X, Instagram, Exa and others | All optional; each isolated with timeout and health state. |

Request path on AWS: browser -> ALB (HTTPS) -> `/api/*` to the API service, everything else to
the web service. Containers live in private subnets; only the ALB is public.

Tenancy: every organization-owned table carries `organization_id`. Every org route resolves an
`OrgContext` (active membership), and non-members get **404, not 403**, so organization ids can't
be probed.

## 3. Authentication

Two modes, chosen by `AUTH_PROVIDER`.

**`local`** (default; email + password)
- Passwords: Argon2 (`pwdlib` recommended hasher), 10-128 characters, no other rules.
- Session: HS256 JWT (12 h) signed with `JWT_SECRET`, claims `sub`, `iss=contentpulse`, `exp`,
  `ver`. Sent as an httpOnly, SameSite=Lax cookie (`cp_session`, `Secure` in production) and
  also returned in the response body, so API clients can use `Authorization: Bearer`.
- Revocation: `users.token_version` is in every token. Sign-out, password change and password
  reset bump it, which ends **all** of that user's sessions.
- Password reset: a 30-minute JWT carrying `purpose=password_reset` and a fingerprint of the
  current password hash, so it works once. Delivered in the URL fragment (never reaches logs).
  Session decoding rejects any token with a `purpose` claim.
- Login timing is equalised for unknown accounts; the response is identical for unknown vs wrong
  password; reset requests answer the same either way.

**`supabase`**
- The web app signs in through Supabase; each API call sends the Supabase access token.
- The API verifies it against the project's JWKS (ES256/RS256/EdDSA, cached 10 min, refetched on
  an unknown `kid`), audience `authenticated`, issuer = your project. Legacy HS256 is accepted if
  `SUPABASE_JWT_SECRET` is set.
- First request provisions or links a user. Linking by email only happens when Supabase itself
  reports the email confirmed (it asks Supabase, not the editable token metadata).

**Invitations**: admin creates a single-use link (only the SHA-256 is stored, 72 h). Accepting as
an existing account requires that account's password (or a matching Supabase session): the link
alone never grants a session. A placeholder account created by an invite can't be claimed through
open registration.

**Rate limits** (Redis-backed, per client IP via `X-Forwarded-For` counted from the right):
600 API requests/min/IP; sign-in 30/IP and 10/account+IP per 15 min (plus 100/account overall);
sign-up 20/h/IP; reset 10/IP and 3/account per hour; invites 30/h; AI endpoints 30/min/user.

## 4. Roles and permissions

Two roles, enforced in the backend (`app/core/permissions.py`); the frontend only hides controls.

| Permission | Admin | Creator |
|---|:-:|:-:|
| View organization, knowledge, trends, topics, content, design | yes | yes |
| Manage topics (shortlist, reject, strategies) | yes | yes |
| Generate and edit content | yes | yes |
| Upload design files, submit for approval | yes | yes |
| Edit organization, brand, platform playbooks | yes | no |
| Knowledge base: crawl, add or exclude pages | yes | no |
| Run trend discovery, edit sources, export CSV | yes | no |
| Assign design tasks | yes | no |
| Approve, request changes, reject, mark final | yes | no |
| Manage team (invite, change role, disable, remove) | yes | no |
| View AI usage | yes | no |

Guards worth knowing: an organization can never lose its last active admin (row-locked check);
state changes go only through the workflow state machines (`app/services/workflow.py`); copy is
editable only while a post is in draft; saves carry `base_version` and a stale save gets 409;
every approval pins the exact copy and creative versions it covered.

**Route coverage check.** A script listed every route that has no auth dependency. The only
ones are the intended public or self-authenticating routes: `GET /auth/config`, `POST
/auth/logout`, `GET /auth/invites/{token}` (unguessable token), `POST /internal/ingest/tick`
(shared secret, 404 unless configured), and the local-storage `PUT/GET /storage/local/{token}`
(signed token). `/auth/register` and `/auth/login` carry rate limits. No unguarded
organization data route was found.

## 5. Workflow and logic, in one pass

1. **Discovery** (scheduler every 3 h by default, or admin "Discover"): each configured source
   runs concurrently; items are normalized, de-duplicated into clusters, scored (popularity,
   growth, freshness, location, source diversity, keyword match). A Postgres advisory lock
   guarantees one scheduler; one active run per organization.
2. **Alignment**: top trends are judged against the organization's profile and knowledge base
   (hybrid full-text + vector search). LLM output is validated in code (unknown services and
   unprovided citations are dropped). With no LLM key a rule engine runs instead.
3. **Topics and strategies**: relevant trends become topic candidates; creators or admins
   shortlist them; per-platform strategies come from an editable playbook.
4. **Content**: approved strategy -> background generation -> versions (never overwritten) ->
   checks for forbidden terms, length, hashtags, CTA.
5. **Design**: sending a post to design creates a brief; creatives go browser -> S3 via presigned
   URL, then are registered (the API re-checks key prefix, size, type) as a new creative version.
6. **Approval**: admins approve, request changes or reject each round; then mark final.

## 6. Findings

Severity is for a first production launch on AWS. "Fix before launch" items are small.

### 6.1 Fix before launch

| # | Finding | Where | Why it matters | Fix |
|---|---|---|---|---|
| F1 | **Terraform can't pass several settings the app needs.** The container environment is a fixed list plus the keys in `secret_keys`. `EMBEDDING_PROVIDER`, `IMAGE_PROVIDER`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_FALLBACKS`, `IMAGE_MODEL`, `TURNSTILE_SITE_KEY` and the `PROVIDER_*` settings are not in it. | `infra/aws/terraform/secrets.tf`, `ecs.tf` | With `EMBEDDING_PROVIDER` unset, knowledge search is **keyword-only** (no semantic search). AI images and model choice can't be configured; Turnstile never shows if you use Supabase CAPTCHA. | Add those names to `local.secret_keys` (empty = unset, because `env_ignore_empty=true`), apply, run `deploy.sh`, then fill them in the secret. |
| F2 | **Presigned S3 uploads may break with current boto3.** `boto3 1.43` computes request checksums by default; browser PUTs to presigned URLs can fail checksum validation. Untested against real S3. | `app/storage/s3.py` | Designers couldn't upload. | Add `request_checksum_calculation="when_required"` and `response_checksum_validation="when_required"` to the `botocore.config.Config(...)`. Test an upload on staging first. |
| F3 | **Database TLS is encrypted but not verified.** For any non-local host the code uses `ssl` with `CERT_NONE`. The AWS stack builds the URL from `DB_HOST`, so it always takes this path. | `app/db/url.py` | A network attacker inside the VPC could impersonate the database. | Bake the RDS CA bundle into the image and use `DATABASE_URL` with `sslmode=verify-full&sslrootcert=...`, or add that option for the `DB_HOST` path. Low likelihood inside a private subnet, but cheap to fix. |
| F4 | **Open registration with no email verification (local mode).** Anyone can create an account and an organization, and each organization can trigger crawls, trend collection and LLM calls. | `POST /auth/register` | Cost abuse and crawler egress from your IPs. Rate limited to 20/h/IP, which does not stop distributed abuse. | Choose one: invite-only (disable register), Supabase Auth with confirmed email + Turnstile, or add email verification. Set `LLM_ORG_DAILY_REQUEST_BUDGET` and provider budgets (`PROVIDER_BUDGET_MODE=enforce`). |
| F5 | **No AWS-side protection around the ALB.** No WAF, no ALB access logs, no alarms, no GuardDuty. | Terraform | Brute force or scanning is invisible; outages go unnoticed. | See section 8.4 (WAF rate rule, ALB logs, CloudWatch alarms). |
| F6 | **Migration `d4b7f2a6c831` (remove viewer) has never run on any database.** | `db/migrations/versions/20261109_...` | Existing viewers become **disabled creators**. The role CHECK constraint is dropped and re-added, which takes a brief table lock. | Back up first (RDS snapshot / `pg_dump`), run in a quiet period, then re-enable the people who should keep access. |
| F7 | **Stray files in the image build context.** `backend/live.tmp.py` and `backend/test-results` are git-ignored but not in `backend/.dockerignore`, so a local `docker build` copies them. | `backend/.dockerignore` | An unknown scratch script (possibly with a key) can end up in an image pushed to ECR. | Add `*.tmp.py`, `test-results`, `.env.bak*` to `.dockerignore` (or delete the files). I did not read `live.tmp.py`. |

### 6.2 Should fix soon

| # | Finding | Detail and fix |
|---|---|---|
| F8 | **CSP does not stop injected scripts yet.** Only `frame-ancestors`, `base-uri`, `object-src`, `form-action` are enforced. The script/style policy is **Report-Only** and allows `'unsafe-inline'`. | React escapes output and no `dangerouslySetInnerHTML` exists in `frontend/src`, so the XSS surface is small. Move to nonce-based CSP when practical. Add `includeSubDomains` to HSTS once every subdomain is HTTPS. |
| F9 | **Session model is coarse.** One bump of `token_version` ends *all* sessions (signing out on a phone signs out the laptop). No MFA, no per-device list, no lockout beyond rate limits, passwords only checked for length. The access token is also returned in the JSON body. | Acceptable for launch. Add MFA (or use Supabase Auth, which has it) before large customers. |
| F10 | **Presigned PUT cannot cap upload size.** The size limit is checked after upload and the object deleted if too big (correct), but for up to 15 minutes an authenticated creator can write a large object. SVG uploads are allowed (rendered from the S3 origin, not yours). | Use presigned POST with `content-length-range` when convenient. Consider sanitising or blocking SVG. |
| F11 | **Account enumeration.** Registration says "An account with this email already exists", and `GET /auth/invites/{token}` reveals the invited email to whoever holds the token. | Low. Rate limits apply. Accept or return a generic message. |
| F12 | **Rate limiting depends on proxy hop count.** `TRUSTED_PROXY_COUNT=1` is right for ALB -> API. If you later add CloudFront or another proxy in front, set it to 2, or every user will share one bucket (a self-inflicted outage). When Redis is unreachable counters fall back to per-task memory. | Document and keep in mind. |
| F13 | **Docs drift.** `docs/architecture.md` says a DNS-rebinding attacker could still race the SSRF check. The code now connects only to the already-validated address (`_PublicOnlyBackend`), so that note is outdated. `docs/production-readiness.md` and `render.yaml` describe the Render/Supabase deployment, not AWS. | Update when convenient. |
| F14 | **Terraform state holds secrets** (`JWT_SECRET`, the Redis token). | Keep the state bucket private, encrypted, versioned, with MFA-protected access. Already encrypted; never commit `*.tfstate`. |
| F15 | **Redis TLS path untested.** The Terraform README says the `rediss://` URL with `ssl_cert_reqs=required` hasn't been run against a real ElastiCache. | After the first deploy, check the worker log shows it connected to the broker (section 8.9). |

### 6.3 Checked and found sound

- Argon2 password hashing, constant-time comparisons for tokens and secrets, hashed invitation tokens.
- Session tokens, reset tokens and file-URL tokens can't be swapped (different `iss`/`aud`/`purpose` checks).
- Supabase token verification pins algorithm, audience and issuer; email linking requires a server-side confirmation.
- Tenant isolation through `OrgContext`; 404 for non-members; child rows fetched by `id AND organization_id`.
- Crawler SSRF protection: public-address-only, re-validated at connect time, redirects checked per hop, no proxy env, 3 MB cap. The ECS task metadata address (169.254.x) is not a global address, so it is refused.
- No raw SQL string building from user input (the only f-string SQL is a constant constraint name in migrations).
- Production refuses to start with the dev `JWT_SECRET` or one under 32 characters, or with `CORS_ORIGINS=*`; `/docs` and OpenAPI are off in production; `/health/metrics` needs a token in production.
- Containers: base images pinned by digest, non-root users, `.env` and keys excluded from images, ECR immutable tags with scan-on-push.
- AWS design: data in private subnets, security groups chained (ALB -> app -> data), RDS storage encrypted with a managed master password (not in state), S3 public access blocked + versioned + encrypted, HTTPS required for `prod`, deployment circuit breaker with rollback, migrations run before any service changes.
- Test suite: 749 passed, 4 skipped (the skips pre-date this work and were not investigated).

---

## 7. Before you touch AWS: checklist

1. Decide `AUTH_PROVIDER`: `local` (simplest; then set up SMTP) or `supabase` (MFA, CAPTCHA, email confirmation; needs Supabase project and redirect URL).
2. Decide registration policy (finding F4).
3. Apply fixes F1, F2, F7 in the repo and commit them (F3 and the rest can follow).
4. **Rotate every API key that has ever been pasted into a chat, ticket or shared file** (`docs/production.md` lists how). Delete `.env.bak-llm`.
5. Pick a region, a domain you control, and a budget alert amount (stack cost is roughly USD 100-150/month before traffic; confirm on the AWS pricing pages).
6. Run the checks locally: `cd backend && uv run ruff check . && uv run pytest`; `cd frontend && npm run lint && npm run typecheck && npm run build`.

## 8. Step-by-step AWS deployment

Everything below uses the Terraform in `infra/aws/terraform` and `infra/aws/deploy.sh`. Use
**Git Bash** on Windows for shell commands (they use bash syntax). Replace `us-east-1`,
`example.com` and `my-` names with your own.

### 8.1 Account setup (console)

1. Create or open your AWS account at <https://console.aws.amazon.com>. Sign in as the **root user** only for the next steps.
2. **Root user -> Security credentials -> MFA**: add an authenticator app.
3. **Billing -> Budgets -> Create budget**: a monthly cost budget with email alerts at 50%, 80%, 100%.
4. **IAM Identity Center** (recommended) or **IAM -> Users**: create an admin user for yourself.
   - Simple path: IAM -> Users -> Create user -> attach `AdministratorAccess` (tighten later) -> enable MFA.
   - Create an **access key** only if you'll use the CLI with keys (IAM -> user -> Security credentials -> Create access key -> "CLI"). Prefer `aws configure sso` if you use Identity Center.
5. Stop using the root user.

### 8.2 Install tools (terminal)

```bash
aws --version         # AWS CLI v2
terraform -version    # 1.6 or newer
docker version        # Docker Desktop running
python --version      # used by deploy.sh to merge secret keys
git --version
```

Install any that are missing (AWS CLI v2, Terraform, Docker Desktop). Then sign in:

```bash
aws configure                 # access key, secret, region (us-east-1), output json
# or: aws configure sso
aws sts get-caller-identity   # must print your account id and user
```

### 8.3 Domain and HTTPS certificate

1. **Route 53 -> Hosted zones** (or your DNS provider). If your domain is elsewhere, you only need to add records there.
2. **Certificate Manager (ACM)** in the **same region as the stack** -> Request -> Public certificate -> `app.example.com` -> DNS validation.
3. Add the CNAME that ACM shows to your DNS, wait until the certificate status is **Issued**, then copy its ARN (`arn:aws:acm:us-east-1:...`).

```bash
aws acm list-certificates --region us-east-1
```

### 8.4 State bucket and lock table (terminal, one time)

The Terraform state must not live on your laptop. Names must be globally unique for the bucket.

```bash
REGION=us-east-1
BUCKET=my-contentpulse-tfstate-$(aws sts get-caller-identity --query Account --output text)

aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
# outside us-east-1 add: --create-bucket-configuration LocationConstraint=$REGION
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws dynamodb create-table --table-name my-contentpulse-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH --billing-mode PAY_PER_REQUEST --region "$REGION"
```

(Console equivalent: S3 -> Create bucket (Block all public access on, Versioning on, default encryption on); DynamoDB -> Create table with partition key `LockID` (String), on-demand.)

### 8.5 Configure the stack (terminal)

```bash
cd infra/aws/terraform
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
```

`backend.hcl` (git-ignored):

```hcl
bucket         = "my-contentpulse-tfstate-<account id>"
region         = "us-east-1"
dynamodb_table = "my-contentpulse-tflock"
```

`terraform.tfvars` (git-ignored):

```hcl
region          = "us-east-1"
environment     = "prod"
domain_name     = "app.example.com"
certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/..."
auth_provider   = "local"      # or "supabase"
llm_provider    = "gemini"     # or "anthropic" / "none"
# db_multi_az   = true         # recommended once real customers use it (roughly doubles database cost)
```

Prod **requires** the certificate; `terraform plan` fails without it.

### 8.6 Create the infrastructure (terminal)

```bash
terraform init -backend-config=backend.hcl
terraform fmt -check && terraform validate
terraform plan -out=tfplan        # read it: VPC, ALB, RDS, Redis, S3, ECR, ECS, IAM, secrets
terraform apply tfplan            # about 15 minutes (the database is the slow part)
```

Services will show failing tasks until images exist. That is expected.

### 8.7 Put your keys in the app secret

Console: **Secrets Manager -> `contentpulse-prod/app` -> Retrieve secret value -> Edit**, set only what you use (everything empty = "not configured"):

- AI: `LLM_API_KEY` (or `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`...), and `EMBEDDING_API_KEY` if using embeddings
- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` (Amazon SES SMTP works: verify your domain, create SMTP credentials, request production access so you leave the SES sandbox)
- Supabase mode: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (and `SUPABASE_JWT_SECRET` only for legacy HS256)
- Operations: `METRICS_TOKEN`, optionally `INGEST_TRIGGER_SECRET`
- Trend sources you pay for: `NEWS_API_KEY`, `GNEWS_API_KEY`, `EXA_API_KEY`, `X_BEARER_TOKEN`, ...

Leave `JWT_SECRET` alone (Terraform generated it). Terminal alternative:

```bash
ARN=$(terraform output -raw app_secret_arn)
aws secretsmanager get-secret-value --secret-id "$ARN" --query SecretString --output text > secret.json
# edit secret.json
aws secretsmanager put-secret-value --secret-id "$ARN" --secret-string file://secret.json
rm secret.json
```

If you applied finding F1 (extra keys such as `EMBEDDING_PROVIDER`), set them here too.

### 8.8 Build, migrate and roll out (terminal)

```bash
cd ../../..                 # repo root
git status                  # commit your changes first: the release tag is the commit id
infra/aws/deploy.sh
```

What it does: logs in to ECR; builds and pushes `api` and `web` images under an immutable tag;
adds any missing secret keys (empty); runs `alembic upgrade head` as a one-off Fargate task
(**stops here if it fails; nothing running changes**); then rolls api, worker, beat and web onto
the new tag and waits until stable. This is the step that applies the viewer-role migration.

Take a manual RDS snapshot before the **first** migration against any database that holds real
data (not needed on a brand-new empty database).

### 8.9 Point your domain at the load balancer

```bash
cd infra/aws/terraform
terraform output load_balancer_dns
```

In Route 53 create an **A (alias)** record for `app.example.com` to the ALB (or a CNAME at another DNS provider). If you use Supabase, add `https://app.example.com/auth/callback` and your site URL in **Authentication -> URL Configuration**.

### 8.10 Verify (smoke test)

```bash
curl -i https://app.example.com/api/v1/auth/config      # 200 and {"provider": ...}
curl -I https://app.example.com/login                   # 200 from the web app
# /health and /health/live are not routed to the API by the ALB (only /api/*), so check the API through
# ECS: the api service's target group should show healthy targets (EC2 -> Target groups).
aws logs tail /ecs/contentpulse-prod --follow --log-stream-name-prefix api
aws logs tail /ecs/contentpulse-prod --since 15m --log-stream-name-prefix worker   # look for a broker connection
aws logs tail /ecs/contentpulse-prod --since 15m --log-stream-name-prefix beat
aws ecs describe-services --cluster contentpulse-prod --services api worker beat web \
  --query 'services[].{n:serviceName,run:runningCount,want:desiredCount}'
```

Then in the browser: register the first account (it becomes an admin of its new organization),
complete onboarding, add the website for the knowledge crawl, invite a teammate (check the email
arrives), upload a test creative (F2), run "Discover trends".

Check that: `/docs` returns 404; the session cookie has `Secure` and `HttpOnly`; HTTP redirects to
HTTPS; the response headers include the CSP and HSTS.

### 8.11 Harden (recommended within the first week)

Console or Terraform; none of this exists yet.

1. **WAF**: AWS WAF -> Web ACL on the ALB with `AWSManagedRulesCommonRuleSet`, `AWSManagedRulesKnownBadInputsRuleSet` and a rate-based rule (for example 2000 requests / 5 min / IP) on `/api/v1/auth/*`.
2. **ALB access logs** to a private S3 bucket (EC2 -> Load balancers -> Attributes).
3. **CloudWatch alarms** (SNS email): ALB 5xx count, target group unhealthy hosts, RDS CPU / free storage / connections, ECS running task count below desired for `beat` and `worker`.
4. **GuardDuty** and **AWS Config / Security Hub** if you need compliance evidence.
5. **RDS**: turn on Multi-AZ (`db_multi_az = true`), Performance Insights, and test a snapshot restore once.
6. **S3**: add a lifecycle rule for old creative versions beyond the 30 days already configured, and enable access logging if required.
7. Move from `AdministratorAccess` to a scoped deploy role; use SSO with MFA for people.

### 8.12 Every release, rollback, and operations

| Task | Command |
|---|---|
| Release | commit, then `infra/aws/deploy.sh` |
| Roll back the app | `cd infra/aws/terraform && terraform apply -var image_tag=<older tag>` (tags are in ECR and `release.auto.tfvars`). Migrations are not reversed; restore a snapshot if a migration must be undone. |
| Logs | `aws logs tail /ecs/contentpulse-prod --follow --log-stream-name-prefix api` (or `worker`, `beat`, `web`, `migrate`) |
| More workers | `services.worker.count` in `terraform.tfvars`, then `terraform apply` (keep `beat` at 1) |
| Rotate a key | edit the secret, then `deploy.sh` or force a new deployment |
| Rotate `JWT_SECRET` | edit the secret, redeploy; everyone is signed out and open reset links die |
| Backups | RDS keeps 7 days of automated backups; add a manual snapshot before risky migrations |
| Tear down (test stacks) | `protect_data = false`, `terraform apply`, then `terraform destroy` |

### 8.13 Common problems

| Symptom | Likely cause |
|---|---|
| `terraform plan` fails on the load balancer | `certificate_arn` missing for `prod` |
| Tasks keep restarting right after first apply | No image yet; run `deploy.sh` |
| Task stops with "secret ... key ... not found" | A key was added to `secret_keys`; run `deploy.sh` (it adds missing keys) |
| Migration task fails | Read `--log-stream-name-prefix migrate`; nothing live changed. Common: database unreachable (security group) or a constraint violated by data |
| Sign-in works but you get logged out | Cookie `Secure` over HTTP, or `FRONTEND_URL`/`CORS_ORIGINS` don't match the real domain |
| Everyone shares one rate-limit bucket | Another proxy was added in front of the ALB; `TRUSTED_PROXY_COUNT` must equal the number of proxies |
| Uploads fail in the browser | Bucket CORS origin does not match the site URL, or finding F2 (checksum) |
| Search is keyword-only | `EMBEDDING_PROVIDER` is not set (finding F1) |

---

## 9. Suggested order of work

1. Fix F1, F2, F7 (an hour or two), commit.
2. Decide registration policy (F4) and the auth mode.
3. Stand up a **staging** stack first (`environment = "staging"`, `protect_data = false`) and run sections 8.1-8.10 end to end, including an upload and an emailed invite.
4. Repeat for `prod`, then do section 8.11 within a week.
5. Schedule: key rotation every 90 days, a restore test, and a dependency update pass.
