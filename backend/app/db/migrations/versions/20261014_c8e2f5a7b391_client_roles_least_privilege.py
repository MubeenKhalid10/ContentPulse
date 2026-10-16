"""least privilege for Supabase client roles on every application table

Revision ID: c8e2f5a7b391
Revises: b4d7f0a5e163
Create Date: 2026-10-14 18:00:00.000000

Browsers never query the database: the web app talks only to the API, and uses
Supabase solely for Auth. The API connects as the tables' owner (the
DATABASE_URL role). So the Supabase Data API roles (`anon`, `authenticated`)
need no access to anything this application creates.

For every table, view and sequence in `public` owned by the migrating role:

- row level security is enabled where it is not already (not forced, no
  policies), which denies every non-owner role that lacks BYPASSRLS; the owner
  is unaffected. Tables that already have it are not altered, so no
  ACCESS EXCLUSIVE lock is taken on them;
- `anon`/`authenticated` lose all privileges (where those roles exist: only on
  Supabase).

For objects the migrating role creates later:

- its `public` default privileges stop granting `anon`/`authenticated` access
  to tables, sequences and functions;
- its global default privileges stop granting EXECUTE on functions to PUBLIC.
  PostgreSQL grants that to every new function unless revoked globally (a
  per-schema revoke can't remove it), and `anon` would inherit it through
  PUBLIC. The owner keeps EXECUTE.

Untouched: `service_role`, schema USAGE, existing functions, objects owned by
other roles (Supabase's own, including the `ensure_rls` event trigger and its
function), and the `auth`/`storage` schemas. Relations in `public` owned by
another role that `anon`/`authenticated` can still reach are reported with a
NOTICE in the migration log, not changed.

Default privileges of other creators (on Supabase, `supabase_admin`) are not
changed: altering them requires membership in that role, which the backend
role normally lacks, and the failure would abort the whole upgrade.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8e2f5a7b391"
down_revision: str | None = "b4d7f0a5e163"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLIENT_ROLES = ("anon", "authenticated")


def harden_sql(roles: Sequence[str]) -> str:
    """Enable RLS and revoke client roles' access on the current user's objects."""
    role_array = ", ".join(f"'{role}'" for role in roles)
    return f"""
DO $$
DECLARE
  obj record;
  client text;
BEGIN
  FOR obj IN
    SELECT c.oid::regclass AS rel FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND c.relowner = current_user::regrole AND NOT c.relrowsecurity
  LOOP
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', obj.rel);
  END LOOP;

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC',
    current_user);

  FOREACH client IN ARRAY ARRAY[{role_array}]::text[] LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = client);
    FOR obj IN
      SELECT c.oid::regclass AS rel, c.relkind FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
        AND c.relowner = current_user::regrole
    LOOP
      EXECUTE format(
        'REVOKE ALL ON %s %s FROM %I',
        CASE WHEN obj.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END, obj.rel, client
      );
    END LOOP;
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
      current_user, client);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
      current_user, client);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I',
      current_user, client);

    -- Not ours to change; make them visible in the deploy log instead.
    FOR obj IN
      SELECT c.oid::regclass AS rel, pg_get_userbyid(c.relowner) AS owner FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
        AND c.relowner <> current_user::regrole
        AND CASE WHEN c.relkind = 'S'
              THEN has_sequence_privilege(client, c.oid, 'USAGE, SELECT, UPDATE')
              ELSE has_table_privilege(
                client, c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
            END
    LOOP
      RAISE NOTICE 'skipped %, owned by %: % can still access it', obj.rel, obj.owner, client;
    END LOOP;
  END LOOP;
END
$$;
"""


def upgrade() -> None:
    # Fail fast instead of queueing behind (and blocking) live traffic: a failed
    # start-up migration leaves the previous deploy serving.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(harden_sql(CLIENT_ROLES))


def downgrade() -> None:
    # Deliberately a no-op: re-granting client roles or disabling RLS would
    # reopen access the application never needed.
    pass
