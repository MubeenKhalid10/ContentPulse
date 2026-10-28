import json
import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_DEV_SECRET = "dev-insecure-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # `KEY=` in .env means "not set", not "empty string" (e.g. a blank
        # JWT_SECRET must fall back to the default and fail the prod check).
        env_ignore_empty=True,
    )

    # Application
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "ContentPulse"
    api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    # A JSON list or a comma-separated list: https://a.example, https://b.example
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    log_level: str = "INFO"

    # Database / Redis
    database_url: str = "postgresql+asyncpg://contentpulse:contentpulse@localhost:5434/contentpulse"
    # Alternative to DATABASE_URL for hosts that keep the password in a managed
    # secret (the AWS stack's RDS-managed password): when DB_HOST and
    # DB_PASSWORD are both set, they build the URL. Unset = nothing changes.
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "contentpulse"
    db_user: str = "contentpulse"
    db_password: str | None = None
    redis_url: str = "redis://localhost:6380/0"

    # Background jobs (Sprint 9).
    #   "inprocess" -> jobs run as asyncio tasks inside the API (default; no
    #                  extra processes needed, good for local use).
    #   "celery"    -> jobs go to Celery workers via CELERY_BROKER_URL (Redis by
    #                  default); scheduling moves to `celery beat`.
    task_backend: Literal["inprocess", "celery"] = "inprocess"
    celery_broker_url: str | None = None  # empty = REDIS_URL
    # Seconds to wait before retrying an AI job that hit a rate limit or outage.
    # One entry per retry; [] disables retries.
    job_retry_delays: list[int] = [30, 120]

    # Rate limiting (spec §61). "auto" uses Redis when reachable (shared across
    # API instances) and falls back to in-memory counters otherwise.
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["auto", "memory", "redis"] = "auto"
    api_rate_limit_per_minute: int = 600  # per client IP, all endpoints
    # Proxies in front of the API that append the client's address to
    # X-Forwarded-For. 0 (default) trusts no header: right for local use, where
    # the Next.js rewrite forwards client-sent headers unchanged. Set 1 behind
    # a load balancer that routes /api to the API directly (the AWS setup).
    trusted_proxy_count: int = 0

    # Authentication
    # "local": email/password with platform-issued JWTs.
    # "supabase": accept Supabase-issued JWTs (users are linked by `sub`).
    auth_provider: Literal["local", "supabase"] = "local"
    jwt_secret: str = _INSECURE_DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12
    session_cookie_name: str = "cp_session"
    # Secure (HTTPS-only) session cookie. Empty = on in production. Set false
    # only for a production-like deployment served over plain HTTP.
    cookie_secure: bool | None = None
    invite_ttl_hours: int = 72
    password_reset_ttl_minutes: int = 30

    # Email (optional). Set SMTP_HOST and SMTP_FROM to email invitations and
    # password-reset links. Unset = invitations show a link to copy and share,
    # and password reset asks the user to contact an admin.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    # "starttls" (port 587), "ssl" (port 465) or "none" (local relay only).
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 15

    # Supabase Auth. SUPABASE_URL is enough for projects using asymmetric
    # signing keys (verified via JWKS); SUPABASE_JWT_SECRET only for legacy HS256.
    # SUPABASE_ANON_KEY is public by design and is served to the web app.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_jwt_secret: str | None = None
    turnstile_site_key: str | None = None

    # AI (used from Sprint 4 onward)
    # LLM for AI alignment and content generation. Unset = rule-based analysis
    # (no AI-written angles); nothing else breaks.
    #   "gemini"    -> Google Gemini (key: LLM_API_KEY or GEMINI_API_KEY)
    #   "anthropic" -> Claude (key: LLM_API_KEY or ANTHROPIC_API_KEY)
    #   "openai", "groq", "cerebras", "openrouter" -> OpenAI-compatible chat
    #                  APIs (key: LLM_API_KEY or <PROVIDER>_API_KEY; LLM_MODEL required)
    #   "none"      -> force rule-based even when a key is set (tests, E2E)
    llm_provider: (
        Literal["gemini", "anthropic", "openai", "groq", "cerebras", "openrouter", "none"] | None
    ) = None
    llm_api_key: str | None = None
    # Empty = the provider's default model (see app/ai/provider.py).
    llm_model: str | None = None
    # Same-provider model tried when the primary is unavailable (spec §56).
    llm_fallback_model: str | None = None
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_timeout_seconds: float = 180.0
    # Keys for providers used as fallbacks (the primary can use LLM_API_KEY).
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    cerebras_api_key: str | None = None
    openrouter_api_key: str | None = None
    # Override an OpenAI-compatible provider's endpoint, e.g. {"openai": "https://..."}.
    llm_base_urls: dict[str, str] = {}

    # LLM gateway (app/ai/gateway.py): every model call is rate limited,
    # retried and recorded here. See docs/llm-gateway.md.
    # Models tried, in order, after the primary model(s) hit a limit or fail:
    # "provider/model" entries, comma-separated (or a JSON list).
    llm_fallbacks: Annotated[list[str], NoDecode] = []
    # Per-workflow model chains, first entry primary, e.g.
    # {"trend_alignment": ["gemini/gemini-3.5-flash", "groq/llama-4-scout"]}.
    llm_routes: dict[str, list[str]] = {}
    llm_fallback_enabled: bool = True
    # Gemini is added as the last cross-provider fallback of every default
    # chain when a Gemini key is set (LLM_ROUTES chains are left as written).
    # Empty LLM_GEMINI_FALLBACK_MODEL turns it off.
    llm_gemini_fallback_model: str | None = "gemini-3.5-flash"
    # Per-model prices for cost_usd on llm_requests (relative to backend/;
    # "off" disables). LLM_PRICES (JSON) overrides entries.
    llm_prices_file: str = "llm_prices.json"
    llm_prices: dict[str, dict] = {}
    # Provider/model limits (RPM, TPM, RPD, TPD, concurrency). Path is relative
    # to backend/; "off" disables the file. LLM_LIMITS (JSON) overrides entries.
    llm_limits_file: str = "llm_limits.json"
    llm_limits: dict[str, dict] = {}
    # Run below published limits: effective limit = limit x factor.
    llm_rate_limit_safety_factor: float = 0.8
    # Concurrent calls per model when its limits don't say.
    llm_max_concurrency: int = 3
    # "auto" shares limits through Redis when reachable (required for several
    # API/worker processes), else counts in process memory.
    llm_limiter_backend: Literal["auto", "memory", "redis"] = "auto"
    # Retries per model for 429/overload/5xx, with exponential backoff + jitter.
    llm_max_retries: int = 2
    llm_retry_base_delay: float = 2.0
    llm_retry_max_delay: float = 60.0
    # How long a call may wait for capacity before giving up (seconds).
    llm_queue_timeout_interactive: float = 20.0
    llm_queue_timeout_background: float = 600.0
    # Cache for repeatable calls (trend analysis, search embeddings). 0 = off.
    llm_cache_ttl_seconds: int = 86400
    # Days of llm_requests history to keep (usage page, cost checks). Older
    # rows are deleted once a day. 0 = keep forever.
    llm_request_retention_days: int = 90
    # Application-wide daily request budgets (empty = no budget).
    llm_daily_request_budget: int | None = None
    llm_org_daily_request_budget: int | None = None
    llm_workflow_daily_budgets: dict[str, int] = {}
    llm_budget_timezone: str = "UTC"
    # Serve Prometheus-format LLM metrics at /health/metrics.
    metrics_enabled: bool = False
    # Optional bearer token scrapers must send to /health/metrics.
    metrics_token: str | None = None
    # Shared secret for POST /api/v1/internal/ingest/tick (an external
    # scheduler such as Supabase Cron). Unset = the endpoint doesn't exist.
    # Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
    ingest_trigger_secret: str | None = Field(default=None, min_length=32)
    # Trends analyzed by AI per discovery run (cost guard). Rule-based analysis
    # covers all recent trends because it is free.
    alignment_ai_batch_size: int = 15
    # Only send a trend to the LLM when the free rule engine finds a keyword,
    # service or knowledge signal; the rest keep the rule-based result.
    alignment_ai_gate: bool = True
    # Automatic re-analysis after failed AI alignment: wait base x 2^(n-1)
    # hours after the n-th failure, and stop after the max. A refused or
    # unusable answer is final until the trend's coverage changes.
    alignment_failure_backoff_hours: float = 3.0
    alignment_max_failures: int = 4
    # Drop collected items that share nothing with the organization's keywords,
    # services or industry before they become trends.
    trend_relevance_prefilter: bool = True
    alignment_auto_analyze: bool = True
    # Embeddings for semantic knowledge search. Unset = keyword-only search.
    #   "openai" -> OpenAI or any OpenAI-compatible API (EMBEDDING_BASE_URL)
    #   "gemini" -> Google Gemini (key: EMBEDDING_API_KEY or GEMINI_API_KEY)
    #   "none"   -> keyword-only even when a key is set (tests, E2E)
    embedding_provider: Literal["openai", "gemini"] | None = None
    # Empty = the provider's default (text-embedding-3-small / gemini-embedding-2).
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_batch_size: int = 64
    # AI images on design tasks ("Generate image with AI").
    #   empty  -> the first provider set up: Kie AI, Cloudflare, Gemini, then OpenAI
    #   "kie" | "cloudflare" | "gemini" | "openai" -> that provider; "none" -> off
    # Gemini image models need billing on the key (the free tier allows 0 images).
    image_provider: Literal["kie", "cloudflare", "gemini", "openai", "none"] | None = None
    # Empty = @cf/black-forest-labs/flux-1-schnell / gemini-2.5-flash-image / gpt-image-1.
    image_model: str | None = None
    # Cloudflare Workers AI (free daily allowance): account id + an API token
    # with "Workers AI" permission. CLOUDFLARE_API_TOKEN works too.
    cloudflare_account_id: str | None = None
    cloudflare_api_key: str | None = None
    cloudflare_api_token: str | None = None
    # Kie AI (pay per image; seedream/5-flash-text-to-image is the cheapest).
    kie_ai_api_key: str | None = None
    # Semantic matches below this cosine similarity are treated as unrelated.
    knowledge_min_similarity: float = 0.2

    # Website crawler
    crawler_user_agent: str = "ContentPulseBot/0.1 (+https://contentpulse.app/bot)"
    crawler_default_max_pages: int = 50
    crawler_max_pages_limit: int = 300
    crawler_concurrency: int = 4
    crawler_timeout_seconds: float = 15.0
    crawler_max_page_bytes: int = 3_000_000
    # Never enable in production: allows fetching private/internal addresses.
    crawler_allow_private_networks: bool = False

    # Creative storage (Sprint 7). With S3_BUCKET set, files go to S3 (or any
    # S3-compatible store via S3_ENDPOINT_URL: R2, MinIO, Supabase Storage).
    # Without it, files go to LOCAL_STORAGE_DIR through signed URLs served by
    # this API — fine for development and single-server installs.
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    aws_region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    local_storage_dir: str = "storage"
    upload_max_mb: int = 100
    signed_url_ttl_seconds: int = 900

    # Trend discovery. Every source is optional: a missing key only marks that
    # source "not configured"; discovery runs with whatever is available.
    trend_source_timeout_seconds: float = 45.0
    trend_scheduler_enabled: bool = True
    # Discovery frequency given to NEW organizations (each organization can
    # change its own; existing organizations keep theirs).
    trend_default_frequency: Literal[
        "manual", "hourly", "every_3_hours", "every_6_hours", "daily"
    ] = "every_3_hours"
    # How often the scheduler checks which organizations are due. A tick only
    # starts runs for organizations whose frequency says they are due; it
    # never refreshes providers by itself.
    trend_scheduler_tick_seconds: int = Field(default=60, ge=10)
    # A run counts as due this much early, so a scheduler tick (or an external
    # trigger every 30 minutes) that lands just before the interval is up
    # doesn't push the run back a whole tick.
    trend_schedule_grace_seconds: int = Field(default=600, ge=0)
    # After a failed or interrupted run (e.g. the server slept), retry after
    # this many minutes, at most this many times in a row; then the normal
    # frequency applies again (no endless retries).
    trend_failure_retry_minutes: int = Field(default=30, ge=1)
    trend_failure_max_retries: int = Field(default=2, ge=0)
    # "Discover New Trends" collects at most once per discovery window: the
    # organization's schedule interval (every 3 hours by default), or the
    # minutes below when background discovery is off. Inside the window the
    # button only reads the stored trends and reports when the next discovery
    # is due; providers are not called.
    trend_manual_reuse_window: bool = True
    trend_manual_window_minutes: int = Field(default=180, ge=1)

    # Shared provider-response cache (app/sources/cache_policy.py). Identical
    # public requests from different organizations reuse one response.
    #   "memory"   -> this process only (lost on restart or Render sleep); default
    #   "postgres" -> also kept in the provider_cache table, shared by every
    #                 process and surviving restarts, for the providers listed
    #                 in PROVIDER_CACHE_PERSIST_SOURCES only
    provider_cache_backend: Literal["memory", "postgres"] = "memory"
    # Providers whose responses may be stored in Postgres. Empty by default:
    # add a provider only after checking its terms allow storing responses
    # and serving them to several customers. Reddit, X and Instagram are never
    # stored (deletion obligations), whatever this says.
    provider_cache_persist_sources: Annotated[list[str], NoDecode] = []
    # Per-policy TTL overrides in seconds, e.g. {"exa": 86400, "google_news": 1800}.
    provider_cache_ttls: dict[str, int] = {}
    # A worker fetching a missing response holds a lease this long; others
    # wait up to provider_cache_wait_seconds for it, then fetch themselves.
    provider_cache_lease_seconds: int = Field(default=60, ge=5)
    provider_cache_wait_seconds: float = Field(default=10.0, ge=0)
    # Expired responses are kept this long (served only while a provider is
    # cooling down) and then deleted.
    provider_cache_stale_seconds: int = Field(default=6 * 3600, ge=0)
    # Responses larger than this are not stored in Postgres.
    provider_cache_max_bytes: int = Field(default=2_000_000, ge=1_000)
    # When the cache database fails: "fetch" calls the provider directly (the
    # run still works, quota is spent); "skip" skips that request instead.
    provider_cache_on_db_error: Literal["fetch", "skip"] = "fetch"

    # Provider request controls (app/sources/quota.py). One platform key per
    # provider serves every organization, so outbound requests (never cache
    # hits) are counted per provider and UTC day before they are sent.
    #   "off"     -> no counting, no limits
    #   "monitor" -> count everything and log what *would* be refused (default)
    #   "enforce" -> refuse requests over a budget, or during a cooldown
    # Cooldowns after rate limits apply in monitor and enforce modes.
    provider_budget_mode: Literal["off", "monitor", "enforce"] = "monitor"
    # Requests per UTC day per provider, e.g. {"gnews": 90, "the_news_api": 90}.
    # Empty = no budget. Set from your real plans: nothing is assumed.
    provider_daily_budgets: dict[str, int] = {}
    # Requests per UTC day one organization may use per provider (fair share).
    provider_org_daily_budgets: dict[str, int] = {}
    # Minutes before the same organization may collect a source again (e.g.
    # repeated manual runs), e.g. {"exa": 360}. Empty = no minimum.
    provider_min_refresh_minutes: dict[str, int] = {}
    # Backoff after a rate limit without Retry-After: base x 2^(streak-1),
    # capped, plus up to 10% jitter. Retry-After is honored up to a day.
    provider_cooldown_base_seconds: int = Field(default=60, ge=1)
    provider_cooldown_max_seconds: int = Field(default=3600, ge=1)
    # Unique hashtags searched per 7 days per Instagram account (Instagram's
    # documented limit is 30; kept below it so manual checks still fit).
    instagram_hashtag_weekly_cap: int = Field(default=27, ge=0, le=30)
    trend_user_agent: str = "ContentPulse/0.1 (trend discovery)"
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    news_api_key: str | None = None
    gnews_api_key: str | None = None
    world_news_api_key: str | None = None
    newsdata_api_key: str | None = None
    the_news_api_key: str | None = None
    exa_api_key: str | None = None
    # Articles per TheNewsAPI request: 3 on the free plan, higher on paid plans.
    the_news_api_limit: int = Field(default=3, ge=1, le=100)
    serp_api_key: str | None = None
    apitube_news_api_key: str | None = None
    x_bearer_token: str | None = None
    x_api_key: str | None = None
    x_api_secret: str | None = None
    instagram_access_token: str | None = None
    instagram_business_account_id: str | None = None
    instagram_graph_version: str = "v21.0"

    @field_validator("llm_provider", "embedding_provider", "image_provider", mode="before")
    @classmethod
    def _known_provider(cls, value: object, info) -> object:
        """A typo in a provider name must not stop the app: an unknown value is
        logged and treated as unset (rule-based / keyword-only)."""
        if not isinstance(value, str):
            return value
        name = value.strip().lower()
        if info.field_name == "embedding_provider" and name == "none":
            return None  # explicitly off (tests, E2E)
        known = {
            "llm_provider": {
                "gemini",
                "anthropic",
                "openai",
                "groq",
                "cerebras",
                "openrouter",
                "none",
            },
            "embedding_provider": {"openai", "gemini"},
            "image_provider": {"kie", "cloudflare", "gemini", "openai", "none"},
        }[info.field_name]
        if name and name not in known:
            import logging

            logging.getLogger("contentpulse").warning(
                "%s=%r is not supported (use one of %s); ignoring it.",
                info.field_name.upper(),
                value,
                ", ".join(sorted(known)),
            )
            return None
        return name or None

    @field_validator(
        "llm_fallbacks", "cors_origins", "provider_cache_persist_sources", mode="before"
    )
    @classmethod
    def _split_models(cls, value: object) -> object:
        """Accept `a/b, c/d` as well as a JSON list, so .env stays readable."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    return json.loads(text)
                except ValueError:
                    text = text.strip("[]")
            return [part.strip(" \"'") for part in text.split(",") if part.strip(" \"'")]
        return value

    @model_validator(mode="after")
    def _database_url_from_parts(self) -> "Settings":
        if self.db_host and self.db_password:
            from urllib.parse import quote

            self.database_url = (
                f"postgresql+asyncpg://{quote(self.db_user, safe='')}:"
                f"{quote(self.db_password, safe='')}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

    @field_validator("cors_origins")
    @classmethod
    def _bare_origins(cls, value: list[str]) -> list[str]:
        # Browsers send origins without a trailing slash; pasted URLs often have one.
        return [origin.rstrip("/") for origin in value]

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.is_production and self.jwt_secret == _INSECURE_DEV_SECRET:
            raise ValueError("JWT_SECRET must be set in production")
        if self.is_production and len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET is too short for production: use at least 32 random characters "
                '(for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`).'
            )
        if "*" in self.cors_origins:
            # Browsers refuse a wildcard with cookies, and allowing it would
            # let any site make credentialed requests: list the real origins.
            raise ValueError("CORS_ORIGINS=* can't be used: list the exact origins instead.")
        if self.auth_provider == "supabase" and not (self.supabase_url and self.supabase_anon_key):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_ANON_KEY are required when AUTH_PROVIDER=supabase"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    # Tests must not depend on a developer's personal .env (API keys etc.).
    if os.environ.get("APP_ENV") == "test":
        return Settings(_env_file=None)
    return Settings()
