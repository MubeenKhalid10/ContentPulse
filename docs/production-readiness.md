# Production readiness: verification and rollout (for approval)

Status: **production not yet verified.** As of 2026-10-14, nothing in
production has been read or changed by the implementation work.

- The Supabase connector available to the assistant can't see project
  `rdhcdeehritzismqfmnc`.
- The Supabase `DATABASE_URL` in the local `.env` is rejected ("password
  authentication failed").

Production state must be established by running the read-only checks below
yourself.

## 1. Run the read-only checks

**Database.** Run `docs/production-verification.sql`.

- It is one `SELECT` that returns one JSON document.
- It doesn't write or change anything.
- It works whether or not the latest migrations have run (missing tables report
  `"table not present"`).
- It has been tested locally on the pre-migration schema (`b7d3e5a1c824`, with
  seeded duplicate active runs) and on the fully migrated schema
  (`b4d7f0a5e163`).

Two ways to run it:

- **As the backend's role (preferred).** This shows its effective privileges.
  Use the *same connection string Render uses*:

  ```
  psql "<Render DATABASE_URL>" -c 'begin read only' -f docs/production-verification.sql -c 'rollback'
  ```

- **Supabase SQL editor.** Paste the file and run it. The editor connects as
  `postgres`, which may differ from the backend's pooler user
  (`postgres.<ref>`), so `identity` and `backend_role` describe the editor's
  role then. Keep the editor's default role (`postgres`): role impersonation
  or a read-only role changes every `current_user`-based check. The script is
  a single `SELECT`, so it is read-only by construction. The psql form above
  additionally enforces a read-only transaction.

**The output can contain sensitive metadata.** It includes role, schema and
object names, ACLs, cron job names and schedules, Vault secret *names*
(never values), connection counts per database user and the Data API's
exposed-schema setting. Review it before sharing, redact anything you
wouldn't publish, and store it with access-controlled records.

Then check these in the Dashboard; they aren't visible in SQL:

- **Project Settings › Data API:** is the Data API enabled, and which schemas
  are exposed (normally `public`)?
- **Advisors › Security Advisor:** list the findings, especially "RLS disabled
  in public".
- **Authentication › Attack Protection (CAPTCHA):** is it enabled? If yes, the
  Turnstile site key must be set on Render (see §3).

## 2. What each check means

| Check (JSON key) | Look for | Why |
|---|---|---|
| `identity`, `backend_role` | role name; `bypass_rls`; `superuser` | The API connects as this role. It must own the tables (migrations `ALTER` them and enable RLS). |
| `public_tables` | owner = backend role; `rls` | Production (2026-10-14) reports `rls: true` on all 30 tables, enabled outside the migrations (most likely by Supabase's managed `ensure_rls` event trigger; confirm its tags in `event_triggers`). The repository enables RLS only in `b4d7f0a5e163` (provider tables) and `c8e2f5a7b391` (every table the backend role owns, where not already on). |
| `policies` | expected `[]` | No RLS policies exist in the repository. |
| `client_role_table_grants` | grants to `anon`/`authenticated` on ContentPulse tables | Supabase grants these by default. **With the Data API exposing `public`, a table that has grants and no RLS can be read and written with the public anon key**, which the web app ships to browsers when `AUTH_PROVIDER=supabase`. |
| `client_roles` | `public_schema_usage`; `public_schema_create` expected `false` for `anon`/`authenticated` | Whether those roles can reach `public` at all, and whether they could create objects there (which could hijack a `SECURITY DEFINER` function that doesn't pin `search_path`). |
| `client_column_privileges` | `explicit_column_grants` expected `[]`; `relations_with_any_column_access`: before `c8e2f5a7b391`, every table with today's broad grants; after it, only relations listed in `public_objects_not_owned_with_client_grants` | Column-level grants aren't visible in `client_role_table_grants`. The first list shows columns with their own ACL and what `anon`/`authenticated` can effectively do on each. The second lists every relation where they can use at least one column, by any route (table grant, column grant, `PUBLIC`, membership). |
| `authenticator_db_schemas` | e.g. `["public, graphql_public"]`, or `[]` | Only the `pgrst.db_schemas` role setting. `[]` means it isn't stored as a role setting. The Dashboard's Data API page is authoritative. |
| `public_functions` | `non_extension` empty apart from Supabase's `ensure_rls` function; `extension_security_definer_client_executable` expected `[]` | For each non-extension function: owner, `security_definer`, `config` (pinned `search_path`), and `anon_execute`/`authenticated_execute` (`null` = role absent). Extension functions are only counted unless they are `SECURITY DEFINER` and executable by a client role. |
| `default_privileges` | grants to `anon`/`authenticated` (and, for functions, `PUBLIC`) by creator; `schema: null` = global | Objects created later inherit them. After `c8e2f5a7b391`, the backend role's rows grant nothing to `anon`/`authenticated`, and its global function row omits `PUBLIC`. `supabase_admin`'s rows stay as they are (§5, limitation). |
| `backend_member_of_supabase_admin` | normally `false` | Whether the backend role could change `supabase_admin`'s default privileges at all. |
| `public_objects_not_owned_with_client_grants` | expected `[]` | Relations in `public` owned by another role that `anon`, `authenticated` or `PUBLIC` can access. `c8e2f5a7b391` doesn't touch them (it logs a NOTICE for each); each one needs a decision. |
| `event_triggers` | Supabase's `ensure_rls` | Tags, owner, the function's schema/owner, `security_definer`, `config` (a pinned `search_path`), ACL, `anon_execute` and `authenticated_execute`. Inspect only; never change or drop Supabase-managed triggers or functions. |
| `extensions` | `pg_cron`, `pg_net`, `supabase_vault` available/installed | Needed for Supabase Cron (Phase 7). |
| `cron_net_functions` | before Stage 5: `[]` is normal; after: every overload of `cron.schedule` and `net.http_post` with `postgres_execute: true`, `anon_execute`/`authenticated_execute: false` | Found by schema and name in the catalogs, so a missing extension, schema or function gives `[]` instead of an error, and overloads with different signatures are all listed. |
| `data.cron_jobs`, `data.vault_secret_names` | existing jobs/secret names | Avoids clashing with `contentpulse-ingest-tick` / `contentpulse_ingest_secret`. Names only, never values. |
| `data.alembic_version` | `b7d3e5a1c824` = before this work; `a3c6e9f4d052` = commit `6932b5f` deployed and migrated; `b4d7f0a5e163` = everything | Tells whether Render auto-deployed `6932b5f` and ran its migrations. |
| `frequency_check_constraint`, `one_active_run_index_present`, `trend_sources_cooldown_columns_present` | match `alembic_version` | Confirms the migrations really applied. |
| `data.duplicate_active_runs` | expected `organizations: 0` | Counts only, with no organization ids: how many organizations hold more than one queued/running run, how many runs that is, and their date range. Migration `e1a4c7d2b830` (already applied in production) marks every **older** duplicate as failed ("superseded") before creating the unique index. Once that index exists, a non-zero count is not possible. |
| `data.active_runs` | `stale` counts | Runs older than 10 minutes without a heartbeat are already treated as interrupted by the app. |
| `data.organization_frequencies` | per frequency | Existing organizations keep these. Only new ones get `every_3_hours`. |
| `data.trend_sources_legacy_errors_with_urls` | count | Old RSS errors with feed URLs still stored. The Phase 1 code hides them from other organizations when it reads them; they're overwritten with sanitized text on the next failure. |
| `data.provider_*_rows` | `"table not present"` or counts | Whether the new tables exist and are in use. |
| `max_connections`, `connections_by_user` | headroom | The scheduler, cache leases and budget ledger use short extra transactions. |

## 3. Render checks (Dashboard, read-only)

1. **Events › Deploys:** did the deploy of commit `6932b5f` succeed, fail, or
   not run? The logs should show `Running upgrade … e1a4c7d2b830`,
   `f2b5d8e3c941` and `a3c6e9f4d052` if `MIGRATE_ON_START` ran them.
2. **Settings:** `autoDeploy` is on in `render.yaml`. **Any push to `main`
   deploys and runs migrations.** Decide whether to keep it on for the next
   steps.
3. **Environment.** Check names and presence only; never copy values.

   | Setting | Expected |
   |---|---|
   | `DATABASE_URL` | Session pooler, **port 5432**. The transaction pooler (6543) breaks advisory locks, the scheduler and DDL. |
   | `APP_ENV` | `production` |
   | `MIGRATE_ON_START` | `true` |
   | `TASK_BACKEND` | `inprocess` |
   | `TREND_SCHEDULER_ENABLED` | `true` |
   | `TRUSTED_PROXY_COUNT` | `2` |
   | `AUTH_PROVIDER` | Note the value. If `supabase`, `SUPABASE_URL` and `SUPABASE_ANON_KEY` must be set, and `TURNSTILE_SITE_KEY` must be set if Supabase CAPTCHA is on. |

   These new settings are **not set yet**; their defaults are safe:

   | Setting | Default |
   |---|---|
   | `PROVIDER_CACHE_BACKEND` | memory |
   | `PROVIDER_BUDGET_MODE` | monitor |
   | `PROVIDER_*_BUDGETS` | empty |
   | `INGEST_TRIGGER_SECRET` | unset → endpoint 404 |
   | `METRICS_ENABLED` | false |

   Provider keys set: list which of `NEWS_API_KEY`, `GNEWS_API_KEY`,
   `WORLD_NEWS_API_KEY`, `NEWSDATA_API_KEY`, `THE_NEWS_API_KEY`, `EXA_API_KEY`,
   `SERP_API_KEY`, `APITUBE_NEWS_API_KEY`, `X_*`, `REDDIT_*` and `INSTAGRAM_*`
   are present. Only those providers matter below.
4. **Plan:** free (sleeps after 15 minutes idle). This determines whether the
   external trigger (Phase 7) is needed.

## 4. Provider plans and terms (before enabling persistence or budgets)

For each provider **with a key on Render**, record:

- the plan;
- its daily or monthly request limit (this sets `PROVIDER_DAILY_BUDGETS`);
- whether the terms allow (a) storing responses, (b) for how long, and (c)
  showing the same results to several customers (organizations);
- any deletion obligations.

| Provider | Known so far | To verify |
|---|---|---|
| NewsAPI | Free Developer plan: development only, **not production**. | Paid plan in use? Otherwise disable the source in production. |
| GNews | `.env.example`: free plan 100 requests/day. | Plan; commercial use; caching terms. |
| TheNewsAPI | `.env.example`: free plan 100/day, 3 articles per request. | Same. |
| NewsData.io | Third-party sources disagree on free-plan commercial use. | Plan; commercial use; caching. |
| World News API, SerpApi, APITube, Exa | Paid or credit based. | Plan limits; storage terms. |
| Reddit | Data API terms require removing deleted content. | Commercial-use terms. **Never persisted** by design. |
| X | Developer agreement requires honoring deletions. | Plan (search is paid). **Never persisted**. |
| Instagram (Meta) | 30 unique hashtags per account per 7 days (vendor docs). Meta limits data storage. | Account type; Public Content Access approval. **Never persisted**. |
| Google Trends / Google News RSS, trendspy | No API terms for these feeds; trendspy is unofficial. | Your risk decision before listing them in `PROVIDER_CACHE_PERSIST_SOURCES`. |
| Hacker News (Algolia) | Public API, no key. | Usage policy. |

## 5. Migration prerequisites

| Migration | Prerequisite / effect | In commit |
|---|---|---|
| `e1a4c7d2b830` | `duplicate_active_runs` reviewed (the older duplicate runs it counts are marked failed). Short lock on `trend_discovery_runs` and `organization_settings` while the index and check constraint are built (small tables). The downgrade maps `every_3_hours` to `every_6_hours`. | `6932b5f` (pushed) |
| `f2b5d8e3c941` | Additive table `provider_cache`. | `6932b5f` (pushed) |
| `a3c6e9f4d052` | Additive tables `provider_usage` and `instagram_hashtag_usage`; three defaulted columns on `trend_sources`. | `6932b5f` (pushed) |
| `b4d7f0a5e163` | Backend role must **own** the three provider tables (`public_tables.owner`). Enables RLS on them where it isn't already on (tables that have it aren't altered or locked) and revokes `anon`/`authenticated` privileges. Touches no other table. Downgrade is a no-op. | uncommitted |
| `c8e2f5a7b391` | For every table/view/sequence in `public` **owned by the backend role**: RLS enabled where it isn't already (not forced, no policies; tables that have it aren't altered or locked), and all `anon`/`authenticated` privileges revoked. For objects the backend role creates later: its `public` default privileges stop granting `anon`/`authenticated` access to tables, sequences and functions, and its **global** default privileges stop granting `EXECUTE` on functions to `PUBLIC` (PostgreSQL's built-in default, which `anon` inherits and which a per-schema revoke can't remove). Existing functions, `service_role`, schema usage, Supabase-owned objects (including `ensure_rls`) and extension functions are untouched; other owners' relations that client roles can reach are logged as NOTICEs. `lock_timeout` 5s. Downgrade is a no-op. | uncommitted |

General prerequisites:

- `DATABASE_URL` on the session pooler (5432).
- A backup or snapshot before migrating. On the Supabase free plan there is no
  PITR, so take a `pg_dump` yourself.
- All migrations run at API start-up (`MIGRATE_ON_START`), inside a transaction.

**Limitation: `supabase_admin`'s default privileges.** Supabase sets default
privileges for objects created by both `postgres` and `supabase_admin`.
`c8e2f5a7b391` corrects only the role it runs as (`postgres`):

- `ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin …` requires membership in
  `supabase_admin`. The backend role normally lacks it
  (`backend_member_of_supabase_admin`). The statement would fail with
  "permission denied to change default privileges", abort the whole upgrade,
  and stop the container from starting. So the migration doesn't attempt it.
- Effect: anything `supabase_admin` creates in `public` later is still granted
  to `anon`/`authenticated` (and functions to `PUBLIC`). In practice that's
  mainly extensions installed into `public`.
- Mitigations:
  - install extensions into the `extensions` schema, not `public`;
  - re-run the verification SQL after any Dashboard change and review
    `public_objects_not_owned_with_client_grants` and
    `public_functions.non_extension`;
  - optionally remove `public` from the Data API's exposed schemas (Stage 1b).

**Behaviour change: no `EXECUTE` to `PUBLIC` on new `postgres` functions.**
`c8e2f5a7b391` removes PostgreSQL's built-in default (`EXECUTE` to `PUBLIC`)
for functions created by the backend role (`postgres`). This is global, not
limited to `public`. A per-schema revoke can't remove that default, and
`anon`/`authenticated` would inherit it.

Existing functions keep their current permissions. From then on, every
function created as `postgres` is executable only by `postgres` until
someone grants it explicitly. That covers:

- functions created by later migrations;
- functions written by hand in the Supabase SQL editor (it runs as
  `postgres`);
- possibly the functions of extensions installed afterwards, if Supabase
  creates them as `postgres`.

The app is unaffected: the backend and Supabase Cron jobs run as `postgres`.
A function meant for another role needs an explicit grant, e.g.
`GRANT EXECUTE ON FUNCTION … TO service_role`. Never grant to `anon`,
`authenticated` or `PUBLIC` without a reviewed design.

This could not be verified locally: the local role is a superuser and has
no Supabase extension manager. Check it after Stage 5.

## 6. Proposed rollout (each stage needs your approval)

| Stage | Action | Go criteria | Rollback |
|---|---|---|---|
| **0** | Run §1–§4 and share the JSON and Render findings. | – | – |
| **1. Close the RLS gap on the new tables** | Commit Phases 5–7 and deploy (push, or a manual deploy with autoDeploy off). `b4d7f0a5e163` runs at start-up. Defaults stay safe. | Stage 0 shows the backend role owns the tables and there are no blocking duplicates. | Set `MIGRATE_ON_START=false` **first**, then redeploy the previous commit: with it `true`, the old image's `alembic upgrade head` fails on the unknown newer revision and the container won't start. The old code runs fine on the newer schema (RLS and revocations don't affect the owner), so no downgrade is needed; the downgrades are no-ops by design. |
| **1b. Existing tables** | `c8e2f5a7b391` (least privilege for `anon`/`authenticated`), deployed with or after Stage 1. Optionally also remove `public` from the Data API's exposed schemas in the Dashboard (the app never uses the Data API). | Stage 0 confirms the backend role owns the tables; `auth_users_triggers` is empty; `public_functions.non_extension` is empty apart from the Supabase-managed `ensure_rls` event-trigger function (if it lives in `public`; inspect it via `event_triggers`, don't change it); `public_objects_not_owned_with_client_grants` is empty or each entry has been reviewed. | Redeploy the previous image (the revocations stay; nothing in the app needs them). Re-grant manually only if something outside the repo turns out to depend on them. |
| **2. Observe** | `METRICS_ENABLED=true` with a `METRICS_TOKEN`. Watch `provider_usage`, cache events and cooldowns for 3–7 days in monitor mode. | Runs succeed; no unexpected `cooling_down`. | Unset the settings. |
| **3. Persistent cache** | Test environment first, then production: `PROVIDER_CACHE_BACKEND=postgres`, `PROVIDER_CACHE_PERSIST_SOURCES=<providers whose terms you verified>`. | Hit rate > 0; no isolation regressions. | `PROVIDER_CACHE_BACKEND=memory` (rows purged within the hour). |
| **4. Budgets** | `PROVIDER_DAILY_BUDGETS` (and per-organization budgets) from the real plans, then `PROVIDER_BUDGET_MODE=enforce`. | Monitor data shows budgets fit normal use. | `PROVIDER_BUDGET_MODE=monitor`. |
| **5. Supabase Cron** | `docs/supabase-cron.md` steps 1–5: Render secret, Vault secret in the Dashboard, extensions, schedule. | Stage 0 shows `pg_cron`/`pg_net` available; Stage 1 deployed. **After installing the extensions**, re-run the verification SQL. In its `cron_net_functions` key, check that every listed overload of `cron.schedule` and `net.http_post` has `postgres_execute: true` (the role that schedules and runs the job) and `anon_execute`/`authenticated_execute: false` (§5, behaviour change). An empty list after installing means the extension or function is missing. Don't use hard-coded signatures: they differ between extension versions, and a missing function raises an error. | `cron.unschedule('contentpulse-ingest-tick')`; unset the secret. |
| **6. Retention** | Choose policies for `raw_data`, Reddit/X text and old runs (proposals in the Phase 5 notes). | Your decision. | – |
