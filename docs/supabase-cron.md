# Supabase Cron trigger for trend discovery

> **Status: prepared, NOT EXECUTED.** Nothing here has been run against any
> Supabase project. Apply it only after the provider cache and quota controls
> are verified in production (docs/provider-cache.md, rollout steps 1–5), and
> after the read-only checks in step 0 pass.

Supabase Cron calls the API every 30 minutes, so discovery runs on schedule even
while the free Render instance would otherwise be asleep. This adds no second
scheduler. Each call runs the API's normal scheduler pass
(`app/workers/scheduler.py: tick`), which:

- closes runs that stopped responding;
- starts runs only for organizations that are due, by their own frequency
  (every 3 hours by default);
- does nothing for everyone else.

Duplicate, late or concurrent deliveries are harmless. An advisory lock lets
one pass schedule at a time, and a unique index allows one active run per
organization. The in-process scheduler keeps running as a backup while the API
is awake.

```
pg_cron (*/30) ──> pg_net http_post ──X-Ingest-Secret──> Render: POST /api/v1/internal/ingest/tick
                                                          └─ scheduler.tick() → due organizations only
```

No Edge Function is needed: pg_net can call the API directly.

**Why every 30 minutes for a 3-hour cadence.** Each organization is collected
once per discovery window: 3 hours after its last successful run, by default.
A 30-minute trigger starts the next run at most 30 minutes after the window
ends, whatever time the last run happened. A fixed `0 */3 * * *` trigger would
skip a whole cycle whenever a run drifted past the slot. Inside the window,
"Discover New Trends" in the app collects nothing: `POST /trends/discover`
returns `started: false` and `next_discovery_at`, and the page shows the stored
trends (`TREND_MANUAL_REUSE_WINDOW`, `app/api/v1/trends.py`).

## 0. Read-only checks (run first, change nothing)

Run these in the Supabase SQL editor of the ContentPulse project:

```sql
-- Extensions available / installed
select name, default_version, installed_version
from pg_available_extensions
where name in ('pg_cron', 'pg_net', 'supabase_vault');

-- The role the API connects as, and whether it bypasses RLS
select current_user, rolsuper, rolbypassrls
from pg_roles where rolname = current_user;

-- RLS on the provider tables (expect true after the migrations)
select relname, relrowsecurity
from pg_class
where relname in ('provider_cache', 'provider_usage', 'instagram_hashtag_usage');

-- What the Data API roles can read in public (expect nothing sensitive)
select table_name, privilege_type, grantee
from information_schema.role_table_grants
where table_schema = 'public' and grantee in ('anon', 'authenticated')
order by table_name;

-- Existing cron jobs (if pg_cron is installed)
select jobid, jobname, schedule, active from cron.job;
```

Also check:

- **Data API:** whether it is enabled and which schemas it exposes
  (Dashboard › Project Settings › Data API).
- **Security Advisor:** its findings (Dashboard › Advisors).

If `pg_cron` or `pg_net` is unavailable, stop. The supported alternative is any
external cron service (cron-job.org, GitHub Actions on a schedule, UptimeRobot)
calling the same endpoint with the same header.

## 1. API configuration (Render), needs approval

Generate a secret locally:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then set it on Render as `INGEST_TRIGGER_SECRET`. It must be at least 32
characters. Without it, the endpoint returns 404.

Test it with the secret in a header, never in the URL:

```
curl -X POST https://<your-render-service>.onrender.com/api/v1/internal/ingest/tick \
     -H "X-Ingest-Secret: $INGEST_TRIGGER_SECRET"
# {"status":"ok","scheduled":N,"recovered":M}
```

A wrong or missing secret returns 401. The endpoint returns 413 for bodies over
1 KB, 429 for more than 6 calls a minute, and 503 when the scheduler or database
fails.

## 2. Store the secret in Vault, needs approval

Prefer the Dashboard (Project Settings › Vault › Add new secret). The value then
never appears in SQL history:

- name: `contentpulse_ingest_secret`
- secret: the value from step 1

The SQL equivalent puts the value in the query history, so avoid it if you can:

```sql
-- NOT EXECUTED
select vault.create_secret('<paste-secret>', 'contentpulse_ingest_secret',
                           'ContentPulse ingest trigger (Render)');
```

## 3. Enable the extensions, needs approval

```sql
-- NOT EXECUTED
create extension if not exists pg_cron;
create extension if not exists pg_net;
```

## 4. Schedule the job, needs approval

```sql
-- NOT EXECUTED
select cron.schedule(
  'contentpulse-ingest-tick',
  '*/30 * * * *',
  $$
  select net.http_post(
    url := 'https://<your-render-service>.onrender.com/api/v1/internal/ingest/tick',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Ingest-Secret', (select decrypted_secret from vault.decrypted_secrets
                          where name = 'contentpulse_ingest_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  );
  $$
);
```

Notes:

- `timeout_milliseconds` is 30 s instead of pg_net's 5 s default. A sleeping
  free Render instance can take about a minute to wake. If the call times out,
  the request has still woken the API, and its in-process scheduler starts the
  due runs within a minute.
- The secret is read from Vault each time the job runs. It isn't in the job
  definition (`cron.job.command` holds only the query that reads it), the URL or
  the logs.
- The tick only schedules organizations that are due, so a 30-minute tick never
  refreshes providers every 30 minutes.

## 5. Check that it works (read-only)

```sql
-- Job runs (succeeded = the request was queued)
select jobid, status, start_time, end_time, return_message
from cron.job_run_details
where jobid = (select jobid from cron.job where jobname = 'contentpulse-ingest-tick')
order by start_time desc limit 10;

-- HTTP results (status_code 200 expected; 401 = secret mismatch)
select id, status_code, timed_out, error_msg, created
from net._http_response order by created desc limit 10;
```

Then check that only due organizations ran:

```sql
select organization_id, trigger, status, created_at
from trend_discovery_runs
where created_at > now() - interval '2 hours'
order by created_at desc;
```

## Change or remove

```sql
-- NOT EXECUTED: change the interval
select cron.alter_job(
  (select jobid from cron.job where jobname = 'contentpulse-ingest-tick'),
  schedule := '*/15 * * * *'
);

-- NOT EXECUTED: remove the job
select cron.unschedule('contentpulse-ingest-tick');
```

To rotate the secret:

1. Update `INGEST_TRIGGER_SECRET` on Render.
2. Update the Vault secret (Dashboard, or
   `vault.update_secret(<id>, '<new>')`).

Ticks in between get a 401 and are retried 30 minutes later.

Removing the job changes nothing else. The in-process scheduler keeps working
while the API is awake.
