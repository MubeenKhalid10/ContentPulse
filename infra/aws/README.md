# Deploying ContentPulse to AWS (optional)

Nothing here is needed to run ContentPulse locally. This folder is a ready
setup for when you want a hosted environment.

## What gets created

```
                      ┌──────────── Application Load Balancer ────────────┐
   browser ──HTTPS──▶ │  /api/*  → API service      everything else → web │
                      └───────────────────────────────────────────────────┘
   private subnets:   ECS Fargate: api (FastAPI) · worker (Celery) · beat (Celery) · web (Next.js)
                      RDS PostgreSQL 17 + pgvector · ElastiCache Redis (broker + rate limits)
   also:              S3 bucket for creatives (presigned uploads) · ECR repositories ·
                      Secrets Manager (DB URL, JWT secret, your API keys) · CloudWatch logs
```

- One backend image runs as the API, the Celery worker and Celery beat; migrations run as a
  one-off task on every deploy, before the services roll.
- Browsers upload creatives straight to S3 with presigned URLs; the bucket only accepts
  them from your app's origin (CORS).
- Every optional integration stays optional: empty keys in the secret mean "not
  configured", exactly like a blank line in your local `.env`.

## Prerequisites

- An AWS account and the AWS CLI, signed in (`aws sts get-caller-identity` works).
- Terraform 1.6+ and Docker.
- A domain and an ACM certificate in the same region. HTTPS is required when
  `environment = "prod"` (the default): `terraform plan` fails without `certificate_arn`.
- An S3 bucket (versioned, encrypted) and a DynamoDB table for Terraform state and locking;
  the one-time commands are in `terraform/backend.hcl.example`.

## First deploy

```bash
cd infra/aws/terraform
cp terraform.tfvars.example terraform.tfvars   # set region, domain, certificate...
cp backend.hcl.example backend.hcl             # your state bucket + lock table (setup steps inside)
terraform init -backend-config=backend.hcl
terraform apply                                # ~15 minutes (the database is the slow part)

# Add your keys (LLM_API_KEY, NEWS_API_KEY, ...) to the app secret:
terraform output app_secret_arn                # edit it in the console, or:
aws secretsmanager get-secret-value --secret-id "$(terraform output -raw app_secret_arn)" \
  --query SecretString --output text > secret.json   # edit, then:
aws secretsmanager put-secret-value --secret-id "$(terraform output -raw app_secret_arn)" \
  --secret-string file://secret.json && rm secret.json

../deploy.sh                                   # build, push, migrate, roll out
terraform output app_url
```

The services start before the first images exist, so they retry until `deploy.sh` has
pushed them. That's expected.

With a domain, point it at `terraform output load_balancer_dns` (a CNAME, or a Route 53
alias), and add `https://your-domain/auth/callback` to Supabase's redirect URLs if you use
Supabase auth.

## Every release

```bash
infra/aws/deploy.sh
```

If migrations fail, the release stops before any service changes. If new tasks fail their
health checks, ECS rolls back automatically (deployment circuit breaker).

## Operating it

| Task | Command |
|------|---------|
| Logs | `aws logs tail /ecs/contentpulse-prod --follow --log-stream-name-prefix api` (or `worker`, `beat`, `web`, `migrate`) |
| More workers | Set `services.worker.count` in `terraform.tfvars`, then `terraform apply` |
| Change a key | Edit the app secret, then `deploy.sh` (or force a new deployment) |
| Tear down | Set `protect_data = false`, `terraform apply`, then `terraform destroy` |

Keep `services.beat.count` at 1; a second beat would schedule everything twice. Terraform
refuses a higher value.

## Cost

With the defaults (one of each service on small Fargate sizes, `db.t4g.micro`,
`cache.t4g.micro`, one NAT gateway and an ALB), expect very roughly USD 100–150 per month in
`us-east-1`, mostly fixed costs (NAT gateway, load balancer, database). Check the AWS
pricing pages for your region before relying on this.

## Notes

- Plain HTTP (no certificate) is only accepted for non-prod stacks (`environment = "staging"`,
  say), and sets `COOKIE_SECURE=false` so email/password sign-in works there. Prod needs HTTPS.
- Images are immutable and addressed by release tag. `deploy.sh` pushes one tag per build,
  migrates from that image first, and only then moves the services to it, so a failed
  migration leaves the running release alone. The running tag is remembered in
  `terraform/release.auto.tfvars`. Roll back with `terraform apply -var image_tag=<old tag>`.
  There is no `:latest`.
- The database password is created and held by RDS in Secrets Manager
  (`manage_master_user_password`), not in this configuration or in Terraform state. The
  containers get it as `DB_PASSWORD`, with `DB_HOST`/`DB_USER`/... as plain settings. On an
  existing stack, the first `apply` hands the password over to RDS and rolls the services:
  do it in a quiet period.
- `TRUSTED_PROXY_COUNT=1`: the load balancer appends the client address, so per-IP rate
  limits see real clients.
- Redis (the Celery queue and rate-limit counters) needs its auth token and TLS: the URL
  (`rediss://:token@...`) lives in its own secret, `<name>/redis`, which Terraform manages. It
  is now an ElastiCache replication group, so the first `apply` on an existing stack replaces
  the Redis node: queued background jobs and rate-limit counters are lost. Do it in a quiet
  period. This hasn't been run against a real ElastiCache yet: check a worker connects.
- The app secret lists every key the containers read (`terraform output secret_keys`: AI
  provider keys, SMTP, metrics and ingest tokens, ...). Empty means not configured. ECS won't
  start a task whose secret lacks a listed key, so `deploy.sh` adds any missing key (empty)
  to your existing secret before rolling out. Run `deploy.sh` right after a `terraform apply`
  that changes the key list.
- The load balancer checks `/health/live` (the process answers), not `/health` (which also
  queries the database), so a short database failover doesn't make ECS replace every task.
- State is in the S3 backend configured by `backend.hcl` (encrypted, locked). An existing local
  state is copied with `terraform init -backend-config=backend.hcl -migrate-state`; delete the
  local `terraform.tfstate*` files afterwards, they hold secrets in plaintext.
