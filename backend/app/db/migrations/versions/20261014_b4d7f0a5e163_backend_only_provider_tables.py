"""backend-only access to the shared provider tables (RLS on, no policies)

Revision ID: b4d7f0a5e163
Revises: a3c6e9f4d052
Create Date: 2026-10-14 16:00:00.000000

The provider tables are read and written only by the API, which connects as
the tables' owner (the DATABASE_URL role). Row level security with no policies
denies every other role that may be granted table access by default (on
Supabase: `anon` and `authenticated`, used by the Data API with the public
key); the owner is unaffected because RLS is enabled but not forced. Where
those Supabase roles exist, their table privileges are revoked as well.

Nothing else changes: existing tables and their access are untouched.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4d7f0a5e163"
down_revision: str | None = "a3c6e9f4d052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("provider_cache", "provider_usage", "instagram_hashtag_usage")
CLIENT_ROLES = ("anon", "authenticated")


def revoke_sql(tables: Sequence[str], roles: Sequence[str]) -> str:
    """REVOKE for roles that exist (they only exist on Supabase)."""
    statements = "\n".join(
        f"    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN\n"
        f"      EXECUTE 'REVOKE ALL ON TABLE {table} FROM {role}';\n"
        "    END IF;"
        for table in tables
        for role in roles
    )
    return f"DO $$\n  BEGIN\n{statements}\n  END\n$$;"


def enable_rls_sql(tables: Sequence[str]) -> str:
    """ENABLE ROW LEVEL SECURITY only where it is off: ALTER TABLE takes an
    ACCESS EXCLUSIVE lock even when nothing changes (Supabase may have enabled
    RLS already)."""
    statements = "\n".join(
        f"    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = '{table}'::regclass) THEN\n"
        f"      EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';\n"
        "    END IF;"
        for table in tables
    )
    return f"DO $$\n  BEGIN\n{statements}\n  END\n$$;"


def upgrade() -> None:
    # Fail fast instead of queueing behind live traffic (see c8e2f5a7b391).
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(enable_rls_sql(TABLES))
    op.execute(revoke_sql(TABLES, CLIENT_ROLES))


def downgrade() -> None:
    # Deliberately a no-op. Privileges are not re-granted (the tables were
    # never meant for clients), and RLS stays on: it may have been enabled
    # before this migration (Supabase can do so outside migrations), so turning
    # it off here could leave the tables less protected than before.
    pass
