-- ContentPulse: production readiness verification (READ-ONLY)
--
-- One SELECT statement. It reads catalog metadata and aggregate counts only:
-- no writes, no DDL, no setting or privilege changes, and no application row
-- contents beyond counts and dates. Run it in the Supabase SQL editor as
-- `postgres` (it shows one JSON result) or in psql inside a read-only
-- transaction:
--
--   psql "$DATABASE_URL" -c 'begin read only' -f docs/production-verification.sql -c 'rollback'
--
-- Tables, schemas, extensions and roles that may not exist (depending on which
-- migrations ran and which extensions are installed) are looked up in the
-- catalogs first, so anything missing gives null or [] instead of an error.
--
-- The output is NOT guaranteed free of sensitive information. It contains
-- infrastructure metadata: role, database and schema names, object names,
-- ACLs, cron job names and schedules, Vault secret NAMES (never values),
-- connection counts per database user, and the Data API's exposed-schema
-- setting. Review it before sharing and keep it with access-controlled
-- records; redact anything you would not publish.
--
with
q(name, sql) as (
  values
    ('alembic_version',
     'select to_jsonb(string_agg(version_num, '',''))::text as v from public.alembic_version'),
    -- Counts only (no organization ids): organizations with more than one
    -- queued/running run, and how many runs they hold in total.
    ('duplicate_active_runs',
     'select jsonb_build_object(
          ''organizations'', count(*),
          ''active_runs'', coalesce(sum(runs), 0),
          ''oldest'', min(oldest), ''newest'', max(newest))::text as v from (
        select count(*) as runs, min(created_at) as oldest, max(created_at) as newest
        from public.trend_discovery_runs
        where status in (''queued'', ''running'')
        group by organization_id having count(*) > 1) d'),
    ('active_runs',
     'select coalesce(jsonb_agg(a), ''[]'')::text as v from (
        select status, trigger, count(*) as runs,
               count(*) filter (where coalesce(heartbeat_at, created_at)
                                < now() - interval ''10 minutes'') as stale,
               min(created_at) as oldest
        from public.trend_discovery_runs
        where status in (''queued'', ''running'') group by 1, 2) a'),
    ('runs_last_14_days',
     'select coalesce(jsonb_agg(r), ''[]'')::text as v from (
        select status, trigger, count(*) as runs from public.trend_discovery_runs
        where created_at > now() - interval ''14 days'' group by 1, 2 order by 1, 2) r'),
    ('organization_frequencies',
     'select coalesce(jsonb_object_agg(trend_frequency, n), ''{}'')::text as v from (
        select trend_frequency, count(*) as n from public.organization_settings group by 1) f'),
    ('organizations',
     'select count(*)::text as v from public.organizations'),
    ('trend_sources_legacy_errors_with_urls',
     'select count(*)::text as v from public.trend_sources where last_error ~* ''https?://'''),
    ('provider_cache_rows', 'select count(*)::text as v from public.provider_cache'),
    ('provider_usage_rows', 'select count(*)::text as v from public.provider_usage'),
    ('instagram_hashtag_usage_rows',
     'select count(*)::text as v from public.instagram_hashtag_usage'),
    ('cron_jobs',
     'select coalesce(jsonb_agg(j), ''[]'')::text as v from (
        select jobid, jobname, schedule, active from cron.job order by jobid) j'),
    ('vault_secret_names',
     'select coalesce(jsonb_agg(name order by name), ''[]'')::text as v from vault.secrets')
),
needs(name, rel) as (
  values
    ('alembic_version', 'public.alembic_version'),
    ('duplicate_active_runs', 'public.trend_discovery_runs'),
    ('active_runs', 'public.trend_discovery_runs'),
    ('runs_last_14_days', 'public.trend_discovery_runs'),
    ('organization_frequencies', 'public.organization_settings'),
    ('organizations', 'public.organizations'),
    ('trend_sources_legacy_errors_with_urls', 'public.trend_sources'),
    ('provider_cache_rows', 'public.provider_cache'),
    ('provider_usage_rows', 'public.provider_usage'),
    ('instagram_hashtag_usage_rows', 'public.instagram_hashtag_usage'),
    ('cron_jobs', 'cron.job'),
    ('vault_secret_names', 'vault.secrets')
),
dyn as (
  -- Runs each query only if its table exists and is readable by this role.
  select q.name,
         case
           when to_regclass(n.rel) is null then '"table not present"'
           when not has_table_privilege(n.rel, 'SELECT') then '"no SELECT privilege"'
           else (xpath('/row/v/text()', query_to_xml(q.sql, false, true, '')))[1]::text
         end as value
  from q join needs n using (name)
)
select jsonb_pretty(jsonb_build_object(
  'checked_at', now(),

  -- 1. Who the connection is (run this with the SAME connection string as
  --    Render's DATABASE_URL to see the backend's effective role).
  'identity', jsonb_build_object(
    'current_user', current_user,
    'session_user', session_user,
    'database', current_database(),
    'server_version', current_setting('server_version'),
    'port', inet_server_port()
  ),
  'backend_role', (
    select jsonb_build_object(
      'rolname', rolname, 'superuser', rolsuper, 'bypass_rls', rolbypassrls,
      'create_role', rolcreaterole, 'member_of',
      (select coalesce(jsonb_agg(r.rolname order by r.rolname), '[]')
       from pg_auth_members m join pg_roles r on r.oid = m.roleid
       where m.member = pg_roles.oid))
    from pg_roles where rolname = current_user
  ),

  -- 2. Tables in public: owner, RLS, forced RLS.
  'public_tables', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'table', c.relname, 'owner', pg_get_userbyid(c.relowner),
      'rls', c.relrowsecurity, 'rls_forced', c.relforcerowsecurity) order by c.relname), '[]')
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p')
  ),
  'policies', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'table', tablename, 'policy', policyname, 'roles', roles, 'cmd', cmd)
      order by tablename, policyname), '[]')
    from pg_policies where schemaname = 'public'
  ),

  -- 3. What the Data API roles may do in public (Supabase grants these by
  --    default; RLS is what stops them).
  'client_role_table_grants', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'grantee', grantee, 'table', table_name, 'privileges', privileges)
      order by table_name, grantee), '[]')
    from (
      select grantee, table_name,
             string_agg(privilege_type, ',' order by privilege_type) as privileges
      from information_schema.role_table_grants
      where table_schema = 'public' and grantee in ('anon', 'authenticated')
      group by grantee, table_name
    ) g
  ),
  -- public_schema_create: whether the role can create objects in public
  -- (expected false for anon/authenticated; with it, a SECURITY DEFINER
  -- function that doesn't pin search_path could be hijacked).
  'client_roles', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'role', rolname, 'bypass_rls', rolbypassrls,
      'public_schema_usage', has_schema_privilege(oid, 'public', 'USAGE'),
      'public_schema_create', has_schema_privilege(oid, 'public', 'CREATE'))
      order by rolname), '[]')
    from pg_roles where rolname in ('anon', 'authenticated', 'service_role', 'authenticator')
  ),
  -- Column-level privileges in public. 'explicit_column_grants': columns that
  -- carry their own ACL, with what anon/authenticated can EFFECTIVELY do on
  -- each (via the column grant, a table grant, PUBLIC or role membership).
  -- 'relations_with_any_column_access': every relation where they can use at
  -- least one column, whether granted per column or per table.
  'client_column_privileges', (
    select jsonb_build_object(
      'explicit_column_grants', (
        select coalesce(jsonb_agg(jsonb_build_object(
          'role', r.rolname, 'relation', c.oid::regclass::text, 'column', a.attname,
          'privileges', to_jsonb(array_remove(array[
            case when has_column_privilege(r.oid, c.oid, a.attnum, 'SELECT') then 'SELECT' end,
            case when has_column_privilege(r.oid, c.oid, a.attnum, 'INSERT') then 'INSERT' end,
            case when has_column_privilege(r.oid, c.oid, a.attnum, 'UPDATE') then 'UPDATE' end,
            case when has_column_privilege(r.oid, c.oid, a.attnum, 'REFERENCES') then 'REFERENCES' end
          ], null)))
          order by r.rolname, c.oid::regclass::text, a.attnum), '[]')
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid
        cross join pg_roles r
        where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f')
          and a.attnum > 0 and not a.attisdropped and a.attacl is not null
          and r.rolname in ('anon', 'authenticated')
          and has_column_privilege(r.oid, c.oid, a.attnum, 'SELECT, INSERT, UPDATE, REFERENCES')
      ),
      'relations_with_any_column_access', (
        select coalesce(jsonb_agg(jsonb_build_object(
          'role', r.rolname, 'relation', c.oid::regclass::text, 'kind', c.relkind::text,
          'rls', c.relrowsecurity)
          order by r.rolname, c.oid::regclass::text), '[]')
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        cross join pg_roles r
        where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f')
          and r.rolname in ('anon', 'authenticated')
          and has_any_column_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE, REFERENCES')
      ))
  ),
  -- Default privileges for objects created later, by creator. 'schema' null =
  -- global (every schema). Type: r tables, S sequences, f functions, T types,
  -- n schemas. Migration c8e2f5a7b391 changes only the backend role's rows;
  -- other creators' rows (supabase_admin) need membership in that role.
  'default_privileges', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'objects_created_by', pg_get_userbyid(d.defaclrole),
      'schema', n.nspname,
      'type', d.defaclobjtype, 'acl', d.defaclacl::text)
      order by pg_get_userbyid(d.defaclrole), n.nspname nulls first, d.defaclobjtype), '[]')
    from pg_default_acl d left join pg_namespace n on n.oid = d.defaclnamespace
    where d.defaclnamespace = 0 or n.nspname = 'public'
  ),
  -- Whether the backend role could change supabase_admin's default privileges.
  'backend_member_of_supabase_admin', (
    select pg_has_role(current_user, oid, 'MEMBER') from pg_roles
    where rolname = 'supabase_admin'
  ),
  -- Relations in public NOT owned by this role that anon, authenticated or
  -- PUBLIC hold privileges on. c8e2f5a7b391 leaves these alone (it reports
  -- them as NOTICEs); each needs a decision.
  'public_objects_not_owned_with_client_grants', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'object', o.rel, 'kind', o.relkind, 'owner', o.owner, 'rls', o.rls,
      'grantee', o.grantee, 'privileges', o.privileges)
      order by o.rel, o.grantee), '[]')
    from (
      select c.oid::regclass::text as rel, c.relkind::text, c.relrowsecurity as rls,
             pg_get_userbyid(c.relowner) as owner,
             case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end as grantee,
             string_agg(a.privilege_type, ',' order by a.privilege_type) as privileges
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      cross join lateral aclexplode(c.relacl) a
      where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
        and c.relowner <> current_user::regrole
        and (a.grantee = 0 or pg_get_userbyid(a.grantee) in ('anon', 'authenticated'))
      group by 1, 2, 3, 4, 5
    ) o
  ),
  -- Only the Data API's exposed-schema setting (pgrst.db_schemas), if it is
  -- stored as a role setting on authenticator; other settings are not
  -- printed. [] = not stored there (database-scoped role settings aren't
  -- read). The Dashboard (Project Settings > Data API) is authoritative.
  'authenticator_db_schemas', (
    select coalesce(jsonb_agg(substr(s.setting, length('pgrst.db_schemas=') + 1)), '[]')
    from pg_roles r cross join lateral unnest(r.rolconfig) as s(setting)
    where r.rolname = 'authenticator' and s.setting like 'pgrst.db\_schemas=%'
  ),
  -- Other Data API surfaces: views (run as their owner unless security_invoker)
  -- and functions callable as RPC (public_functions, below).
  'public_views', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'view', c.relname, 'owner', pg_get_userbyid(c.relowner),
      'security_invoker', coalesce(c.reloptions::text ~ 'security_invoker=(on|true)', false),
      'anon_select', has_table_privilege('anon', c.oid, 'SELECT'))
      order by c.relname), '[]')
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('v', 'm')
      and exists (select 1 from pg_roles where rolname = 'anon')
  ),
  -- Functions in public (callable as RPC by roles with EXECUTE).
  -- non_extension: every one, with owner, SECURITY DEFINER, pinned settings
  -- (search_path) and whether anon/authenticated can execute it (null = role
  -- absent). extension_security_definer_client_executable: extension-owned
  -- SECURITY DEFINER functions those roles can execute (pure SECURITY INVOKER
  -- helpers such as vector's are only counted).
  'public_functions', (
    select jsonb_build_object(
      'non_extension', coalesce(jsonb_agg(jsonb_build_object(
        'function', f.signature, 'owner', f.owner,
        'security_definer', f.security_definer, 'config', f.config,
        'anon_execute', f.anon_execute, 'authenticated_execute', f.authenticated_execute)
        order by f.signature) filter (where f.extension is null), '[]'),
      'extension_security_definer_client_executable', coalesce(jsonb_agg(jsonb_build_object(
        'function', f.signature, 'extension', f.extension, 'owner', f.owner,
        'anon_execute', f.anon_execute, 'authenticated_execute', f.authenticated_execute)
        order by f.signature) filter (
          where f.extension is not null and f.security_definer
            and (f.anon_execute or f.authenticated_execute)), '[]'),
      'extension_owned_count', count(*) filter (where f.extension is not null))
    from (
      select p.oid::regprocedure::text as signature, pg_get_userbyid(p.proowner) as owner,
             p.prosecdef as security_definer, p.proconfig as config, e.extname as extension,
             (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                from pg_roles r where r.rolname = 'anon') as anon_execute,
             (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                from pg_roles r where r.rolname = 'authenticated') as authenticated_execute
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
      left join pg_depend d on d.classid = 'pg_proc'::regclass and d.objid = p.oid
        and d.refclassid = 'pg_extension'::regclass and d.deptype = 'e'
      left join pg_extension e on e.oid = d.refobjid
      where n.nspname = 'public'
    ) f
  ),
  -- Event triggers and their functions (e.g. Supabase's managed ensure_rls,
  -- which enables RLS on new tables). Inspect only; do not change or drop.
  -- tags: the commands it fires on (null = all). search_path: from proconfig;
  -- a SECURITY DEFINER function should pin it.
  'event_triggers', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'name', e.evtname, 'event', e.evtevent, 'enabled', e.evtenabled,
      'tags', e.evttags, 'owner', pg_get_userbyid(e.evtowner),
      'function', p.oid::regprocedure::text,
      'function_schema', pn.nspname,
      'function_owner', pg_get_userbyid(p.proowner),
      'security_definer', p.prosecdef,
      'config', p.proconfig,
      'acl', coalesce(p.proacl::text, 'default (EXECUTE to PUBLIC)'),
      'anon_execute', (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                         from pg_roles r where r.rolname = 'anon'),
      'authenticated_execute', (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                                  from pg_roles r where r.rolname = 'authenticated'))
      order by e.evtname), '[]')
    from pg_event_trigger e
    join pg_proc p on p.oid = e.evtfoid
    join pg_namespace pn on pn.oid = p.pronamespace
  ),
  -- Supabase Cron functions the ingest job uses. Catalog lookup by schema and
  -- name, so a missing extension, schema or function gives [] (not an error)
  -- and every overload is listed. postgres_execute: the role the job is
  -- scheduled and run as (null = no such role).
  'cron_net_functions', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'function', p.oid::regprocedure::text, 'extension', e.extname,
      'owner', pg_get_userbyid(p.proowner), 'security_definer', p.prosecdef,
      'postgres_execute', (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                             from pg_roles r where r.rolname = 'postgres'),
      'anon_execute', (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                         from pg_roles r where r.rolname = 'anon'),
      'authenticated_execute', (select has_function_privilege(r.oid, p.oid, 'EXECUTE')
                                  from pg_roles r where r.rolname = 'authenticated'))
      order by p.oid::regprocedure::text), '[]')
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_depend d on d.classid = 'pg_proc'::regclass and d.objid = p.oid
      and d.refclassid = 'pg_extension'::regclass and d.deptype = 'e'
    left join pg_extension e on e.oid = d.refobjid
    where (n.nspname = 'cron' and p.proname = 'schedule')
       or (n.nspname = 'net' and p.proname = 'http_post')
  ),
  -- Supabase Auth must not depend on public tables (the app provisions users
  -- itself from the JWT); triggers here would.
  'auth_users_triggers', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'trigger', t.tgname, 'function', t.tgfoid::regproc::text) order by t.tgname), '[]')
    from pg_trigger t
    where to_regclass('auth.users') is not null and t.tgrelid = to_regclass('auth.users')
      and not t.tgisinternal
  ),

  -- 4. Extensions for Supabase Cron.
  'extensions', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'name', name, 'available', default_version, 'installed', installed_version)
      order by name), '[]')
    from pg_available_extensions
    where name in ('pg_cron', 'pg_net', 'supabase_vault', 'pgsodium', 'vector')
  ),

  -- 5. Migration state and what migration e1a4c7d2b830 would touch.
  'frequency_check_constraint', (
    select pg_get_constraintdef(oid) from pg_constraint
    where conname = 'ck_organization_settings_trend_frequency'
  ),
  'one_active_run_index_present', exists (
    select 1 from pg_indexes where indexname = 'uq_trend_discovery_runs_one_active'
  ),
  'trend_sources_cooldown_columns_present', exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'trend_sources'
      and column_name = 'cooldown_until'
  ),

  -- 6. Connections (pooler sizing).
  'max_connections', current_setting('max_connections'),
  'connections_by_user', (
    select coalesce(jsonb_object_agg(coalesce(usename, '(internal)'), n), '{}')
    from (select usename, count(*) as n from pg_stat_activity group by 1) s
  ),

  'data', (select jsonb_object_agg(name, value::jsonb) from dyn)
));
