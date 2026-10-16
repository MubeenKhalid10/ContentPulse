# Trend collection: scheduling, shared provider cache and quota controls

How ContentPulse collects trends for many organizations without calling each
provider once per organization, and without one organization using up a
provider key that every organization shares.

## What runs when

- Each organization has a **discovery frequency**: hourly, every 3 hours (the
  default for new organizations), every 6 hours, daily at 08:00 local time, or
  manual only. Existing organizations keep the frequency they chose.
- The **scheduler tick** (every `TREND_SCHEDULER_TICK_SECONDS`, 60 s by default,
  while the API is awake) only checks who is due. It never refreshes providers
  on its own. A run may start up to `TREND_SCHEDULE_GRACE_SECONDS` (10 min) early,
  so a 30-minute external tick keeps a 3-hour cadence.
- A tick first closes runs that stopped responding (after 10 minutes without a
  heartbeat), then starts due runs. A failed or interrupted run is retried after
  `TREND_FAILURE_RETRY_MINUTES` (30), at most `TREND_FAILURE_MAX_RETRIES` (2)
  times in a row. After that, the normal frequency applies again.
- **At most one queued or running run per organization**, enforced by the
  database (`uq_trend_discovery_runs_one_active`). Concurrent manual and
  scheduled triggers, and duplicate ticks, are harmless: the loser gets a 409
  (manual) or does nothing (scheduled).

### Render free plan

The in-process scheduler and the in-memory cache live inside the API process.
Render's free plan sleeps the service after 15 minutes without traffic and
restarts it on deploys. As a result:

- Scheduled runs only happen while the API is awake. An external trigger fixes
  this; see "Supabase Cron" below, which is not enabled yet.
- A run interrupted by sleep or a restart is marked failed on the next start or
  tick and retried after 30 minutes.
- `PROVIDER_CACHE_BACKEND=memory` loses everything on sleep or restart. With
  `postgres`, the opted-in providers' responses survive.
- Rate limits for the LLM and API (`RATE_LIMIT_BACKEND=memory`) also reset on
  restart. Provider cooldowns and budgets are stored in Postgres, so they don't.

## Personalized collection

Searches use the organization's tracked keywords, then its active services.
Without either, they use seed searches for its **industry**
(`backend/app/services/trends/industry.py`): for example, a healthcare clinic
searches "healthcare", "medical technology" and "digital health". Searches never
fall back to a generic topic. With no keywords, services or industry, search-only
sources are skipped, and the run says why.

Markets set the country and language. The organization's default language is
used where a market doesn't imply one. The Technology-only Google Trends source
is switched on by default only for organizations whose industry is technology.

The shared cache only ever holds public provider responses. Clustering,
matching, scoring, AI alignment, knowledge search and generated content all run
per organization, as before.

## Shared provider cache

`backend/app/sources/cache_policy.py` lists, per provider:

- the TTL
- the parameters that change the result
- which parameters are secrets
- how to normalize each parameter

The cache key is a SHA-256 of the provider, endpoint and normalized parameters:

- It describes **what was asked, never who asked**.
- It never contains API keys, tokens or headers.
- Times are rounded down to the TTL bucket.
- Lists of countries are sorted.
- Single-keyword searches are case-folded. Packed `a OR b` queries are not.
- A request with any parameter the policy doesn't know is not shared.

| Provider | TTL | Stored in Postgres? |
|---|---|---|
| Google Trends RSS, Google News | 45 min | opt-in |
| Google Trends Technology (trendspy) | 60 min | opt-in |
| Hacker News | 20 min | opt-in |
| NewsAPI, GNews, World News, NewsData, TheNewsAPI, SerpApi, APITube | 2 h | opt-in |
| Exa | 12 h | opt-in |
| Reddit | 20 min | **never** (memory only) |
| X | 1 h | **never** (memory only) |
| Instagram hashtag id / top media | 30 days / 24 h | **never** (memory only, per token) |
| RSS feeds (organization-owned URLs) | – | never cached |

TTLs are engineering defaults, not statements about what providers allow.
Override them with `PROVIDER_CACHE_TTLS`.

**Provider terms.** Storing responses and serving them to several customers is
a licensing question. Nothing is stored in Postgres until the provider is listed
in `PROVIDER_CACHE_PERSIST_SOURCES`. Status when this was written:

- NewsAPI's free Developer plan does not allow production use at all.
- Reddit's Data API terms and X's developer agreement require deleted content to
  be removed from stored copies.
- Meta limits storing platform data.
- No authoritative caching terms were found for GNews, NewsData, World News,
  TheNewsAPI, SerpApi, APITube, Exa, or Google's public RSS feeds.

Verify each provider before listing it.

**Concurrency.**

- Within one process, identical requests wait for a single fetch.
- Across processes, the first worker to miss takes a short lease (60 s) in
  `provider_cache`. Others wait up to 10 s for its result, then fetch themselves.
- No transaction is open during the provider call.
- A lease left by a killed worker expires and is taken over.
- If the cache database fails, `PROVIDER_CACHE_ON_DB_ERROR=fetch` calls the
  provider directly, and `skip` skips the request.

**Retention and deletion.**

- Hourly housekeeping deletes responses that expired more than
  `PROVIDER_CACHE_STALE_SECONDS` (6 h) ago and dead leases, in bounded batches.
- It also deletes every stored copy of a provider that may no longer be stored.
- To purge at once (e.g. a deletion request):
  `python -m app.sources.cache_admin purge --source <key>`.
- `status` shows rows and bytes per provider.

## Budgets, cooldowns and the Instagram hashtag limit

Every outbound request is checked first. Cache hits are never counted.

- **Cooldowns.** A 429 or 402 response pauses the provider for every
  organization:
  - It honors `Retry-After`.
  - A 402 waits until after midnight UTC.
  - Otherwise it backs off from 60 s, doubling up to 1 h, plus jitter.
  - A recent stored copy is served meanwhile if the provider is opted in.
- **Budgets.** Requests are reserved atomically in `provider_usage` per
  provider, per UTC day, and per organization. Set them in
  `PROVIDER_DAILY_BUDGETS` and `PROVIDER_ORG_DAILY_BUDGETS`.
  `PROVIDER_BUDGET_MODE` can be:
  - `monitor` (default): counts and logs overruns.
  - `enforce`: refuses requests over budget.
  - `off`: disables budgets.
- **Instagram.** Instagram allows 30 unique hashtags per account per 7 days,
  shared by every organization. The ledger `instagram_hashtag_usage` counts
  unique hashtags in a rolling window. Only real searches count. The cap is
  `INSTAGRAM_HASHTAG_WEEKLY_CAP` (27).
- **Minimum refresh.** `PROVIDER_MIN_REFRESH_MINUTES` stops one organization
  re-collecting a source too often.

Run results report deliberate skips as `budget_exhausted`, `cooling_down` or
`skipped_recent`, not as failures. Skips don't mark the provider unhealthy.

## Database access

`provider_cache`, `provider_usage` and `instagram_hashtag_usage` are
backend-only:

- Row level security is enabled with no policies.
- Supabase's `anon` and `authenticated` roles have their privileges on these
  tables revoked.
- The API's own role owns the tables and is unaffected.
- No API endpoint returns their rows.

Platform-wide source health (`trend_sources`) stores only fixed, sanitized
error text. An organization's RSS errors, which can contain its feed URLs, stay
in that organization's own runs.

## Metrics

With `METRICS_ENABLED=true`, `/health/metrics` adds:

- `trend_provider_requests_total`, by outcome
- `trend_provider_latency_seconds`
- `trend_provider_cache_events_total` (memory/db hits, misses, lease waits,
  stale serves, DB errors)
- `trend_provider_usage_today`, `trend_provider_budget_remaining` and
  `trend_provider_cooldown_seconds`
- `trend_discovery_runs_total`, `trend_discovery_duration_seconds` and
  `trend_discovery_active_runs`
- `trend_organizations_by_frequency`
- scheduler counters

Labels are provider keys and statuses only. Set `METRICS_TOKEN` to require
`Authorization: Bearer <token>`.

## Rollout

1. Deploy with the defaults: `PROVIDER_CACHE_BACKEND=memory`,
   `PROVIDER_BUDGET_MODE=monitor`. Migrations are additive.
2. Watch `provider_usage` and the metrics for a few days to learn real request
   volumes.
3. In a non-production environment, set `PROVIDER_CACHE_BACKEND=postgres` and
   list the providers whose terms you have verified. Check cache hit rates, run
   results and tenant isolation.
4. Enable it in production (needs approval).
5. Set `PROVIDER_DAILY_BUDGETS` from the real plans, then
   `PROVIDER_BUDGET_MODE=enforce` (needs approval).
6. New organizations already default to every 3 hours.
7. Add the external Supabase Cron trigger last.

## Rollback

| Change | How to undo |
|---|---|
| Persistent cache | `PROVIDER_CACHE_BACKEND=memory`. Stored rows are purged by the next hourly housekeeping. |
| Budget enforcement | `PROVIDER_BUDGET_MODE=monitor` (or `off`). |
| A stuck cooldown | `UPDATE trend_sources SET cooldown_until = NULL WHERE key = '<source>'`. |
| Default frequency for new organizations | `TREND_DEFAULT_FREQUENCY=daily`. |
| Schema | `alembic downgrade b7d3e5a1c824`. Drops the new tables and columns and the one-active-run index, and maps `every_3_hours` organizations to `every_6_hours`. Only needed if the code is rolled back too. |

## Troubleshooting

- **A source shows `cooling_down` in every run.** Check
  `trend_provider_cooldown_seconds` or `trend_sources.cooldown_until`. The
  provider returned 429 or 402. Review its plan or lower the request volume.
- **`budget_exhausted`.** The UTC day's budget is used up. It resets at
  00:00 UTC.
- **No cache hits across organizations.** Their requests differ: different
  keywords, markets or languages. Only identical questions are shared. Keyword
  searches overlap only when keywords do.
- **`uncacheable` cache events.** An adapter sent a parameter its policy
  doesn't list. Add it to the policy if it changes results, or to
  `secret_params` if it is a credential.
