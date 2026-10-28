# One Secrets Manager secret holds everything sensitive, as JSON. Terraform
# writes the generated values once; add your own keys (LLM_API_KEY, NEWS_API_KEY,
# SUPABASE_*, ...) in the AWS console or with
#   aws secretsmanager put-secret-value --secret-id <app_secret_arn> --secret-string file://secret.json
# and then redeploy. Terraform never overwrites your edits (ignore_changes).
# Empty values mean "not configured": every integration stays optional.

resource "random_password" "jwt" {
  length  = 64
  special = false
}

locals {
  # Keys exposed to the containers. Add a key here AND in the secret to pass a new one.
  secret_keys = [
    "JWT_SECRET",
    "LLM_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "OPENROUTER_API_KEY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "METRICS_TOKEN",
    "INGEST_TRIGGER_SECRET",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "KIE_AI_API_KEY",
    "THE_NEWS_API_KEY",
    "EXA_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_JWT_SECRET",
    "EMBEDDING_API_KEY",
    "NEWS_API_KEY",
    "GNEWS_API_KEY",
    "WORLD_NEWS_API_KEY",
    "NEWSDATA_API_KEY",
    "SERP_API_KEY",
    "APITUBE_NEWS_API_KEY",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "X_BEARER_TOKEN",
    "X_API_KEY",
    "X_API_SECRET",
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
  ]
}

# The Redis connection string carries the auth token, so it lives in its own
# secret (managed here, unlike the app secret you edit by hand).
resource "aws_secretsmanager_secret" "redis" {
  name                    = "${local.name}/redis"
  recovery_window_in_days = var.protect_data ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id = aws_secretsmanager_secret.redis.id
  secret_string = jsonencode({
    REDIS_URL = "rediss://:${random_password.redis.result}@${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0?ssl_cert_reqs=required"
  })
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  recovery_window_in_days = var.protect_data ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(merge(
    { for key in local.secret_keys : key => "" },
    {
      JWT_SECRET = random_password.jwt.result
    },
  ))

  lifecycle {
    ignore_changes = [secret_string]
  }
}
