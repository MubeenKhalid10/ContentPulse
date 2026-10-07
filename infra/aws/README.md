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
- Optional but recommended: a domain and an ACM certificate in the same region, for HTTPS.

## First deploy

```bash
cd infra/aws/terraform
cp terraform.tfvars.example terraform.tfvars   # set region, domain, certificate...
terraform init
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

- HTTP-only deploys (no certificate) set `COOKIE_SECURE=false` so email/password sign-in
  works. Use HTTPS for anything real.
- `TRUSTED_PROXY_COUNT=1`: the load balancer appends the client address, so per-IP rate
  limits see real clients.
- State is local by default. To share it, enable the S3 backend in `versions.tf`.
