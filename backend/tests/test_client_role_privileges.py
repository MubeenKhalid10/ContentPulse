"""Nothing the application stores is reachable without going through the API.

The database side stands in for Supabase's Data API roles (`anon`,
`authenticated`) with a throwaway role that gets Supabase's default grants; the
HTTP side checks that every API route outside a short public list refuses
anonymous callers.
"""

import importlib
import re
import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine
from app.main import app

MIGRATION = importlib.import_module(
    "app.db.migrations.versions.20261014_c8e2f5a7b391_client_roles_least_privilege"
)

OWNED_TABLES = """
    SELECT c.oid::regclass::text FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind::text = :kind AND c.relowner = current_user::regrole
"""


@pytest.fixture
async def supabase_like_role():
    """A role with the access Supabase gives `anon`/`authenticated` by default."""
    name = f"cp_client_{uuid.uuid4().hex[:8]}"
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {name} NOLOGIN"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {name}"))
        await conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {name}"))
        await conn.execute(text(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {name}"))
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            await conn.execute(
                text(
                    f"ALTER DEFAULT PRIVILEGES FOR ROLE current_user IN SCHEMA public "
                    f"GRANT ALL ON {kind} TO {name}"
                )
            )
    try:
        yield name
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP OWNED BY {name}"))
            await conn.execute(text(f"DROP ROLE {name}"))


async def owned(conn, kind: str) -> list[str]:
    return list((await conn.execute(text(OWNED_TABLES), {"kind": kind})).scalars())


async def test_every_application_table_has_rls_without_policies():
    async with engine.connect() as conn:
        tables = await owned(conn, "r")
        state = await conn.execute(
            text(
                "SELECT oid::regclass::text, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid::regclass::text = ANY(:t)"
            ),
            {"t": tables},
        )
        policies = await conn.scalar(text("SELECT count(*) FROM pg_policies"))
    assert "organizations" in tables and "alembic_version" in tables
    assert {name: (rls, forced) for name, rls, forced in state} == {
        t: (True, False) for t in tables
    }
    assert policies == 0


async def test_client_role_with_default_grants_reads_and_writes_nothing(client, supabase_like_role):
    # Today's production shape: broad grants, RLS on, no policies.
    from tests.conftest import create_org, register

    await create_org(await register(client, "owner@alpha.example.com"), "Alpha")
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM organizations")) == 1
        await conn.execute(text(f"SET ROLE {supabase_like_role}"))
        for table in ("organizations", "users", "organization_settings", "provider_cache"):
            assert await conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0, table
        assert (await conn.execute(text("UPDATE organizations SET name = 'x'"))).rowcount == 0
        assert (await conn.execute(text("DELETE FROM users"))).rowcount == 0
        with pytest.raises(Exception, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug) "
                    "VALUES (gen_random_uuid(), 'x', 'x')"
                )
            )
        await conn.rollback()


async def test_hardening_revokes_existing_and_future_client_access(supabase_like_role):
    role = supabase_like_role
    async with engine.begin() as conn:
        await conn.execute(text(MIGRATION.harden_sql([role])))
        await conn.execute(text(MIGRATION.harden_sql([role, "no_such_role_xyz"])))  # idempotent

    async with engine.connect() as conn:
        for table in await owned(conn, "r"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES"):
                allowed = await conn.scalar(
                    text("SELECT has_table_privilege(:r, :t, :p)"),
                    {"r": role, "t": table, "p": privilege},
                )
                assert allowed is False, (table, privilege)
        for sequence in await owned(conn, "S"):
            allowed = await conn.scalar(
                text("SELECT has_sequence_privilege(:r, :s, 'USAGE')"), {"r": role, "s": sequence}
            )
            assert allowed is False, sequence
        leftover = await conn.scalar(
            text("SELECT count(*) FROM pg_default_acl WHERE defaclacl::text ~ :r"), {"r": role}
        )
        assert leftover == 0

    # A table created by a later migration doesn't hand the client role access.
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("CREATE TABLE cp_future_table (id serial PRIMARY KEY)"))
        allowed = await conn.scalar(
            text("SELECT has_table_privilege(:r, 'cp_future_table', 'SELECT')"), {"r": role}
        )
        await trans.rollback()
    assert allowed is False


async def test_new_functions_are_not_executable_by_client_roles(supabase_like_role):
    role = supabase_like_role
    async with engine.connect() as conn:
        trans = await conn.begin()
        # Control: PostgreSQL's built-in default (EXECUTE to PUBLIC) lets the
        # client role run a new function even without its own grant.
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES FOR ROLE current_user GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
            )
        )
        await conn.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE current_user IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM {role}"
            )
        )
        await conn.execute(
            text("CREATE FUNCTION cp_before() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        )
        before = await conn.scalar(
            text("SELECT has_function_privilege(:r, 'cp_before()', 'EXECUTE')"), {"r": role}
        )

        await conn.execute(text(MIGRATION.harden_sql([role])))
        await conn.execute(
            text("CREATE FUNCTION cp_after() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        )
        after = await conn.scalar(
            text("SELECT has_function_privilege(:r, 'cp_after()', 'EXECUTE')"), {"r": role}
        )
        # Distinct text: asyncpg would otherwise reuse the owner's prepared
        # plan, in which the SQL function is already inlined.
        owner_result = await conn.scalar(text("SELECT cp_after() AS owner_call"))
        await conn.execute(text(f"SET ROLE {role}"))
        with pytest.raises(Exception, match="permission denied for function cp_after"):
            await conn.execute(text("SELECT cp_after()"))
        await trans.rollback()
    assert before is True
    assert after is False
    assert owner_result == 1


async def test_hardening_skips_rls_tables_without_locking_them(supabase_like_role):
    # Production already has RLS on every table: hardening must not queue for
    # an ACCESS EXCLUSIVE lock behind live readers.
    async with engine.connect() as reader, engine.connect() as migrator:
        await reader.begin()
        await reader.execute(text("LOCK TABLE organizations IN ACCESS SHARE MODE"))
        trans = await migrator.begin()
        await migrator.execute(text("SET LOCAL lock_timeout = '1s'"))
        await migrator.execute(text("CREATE TABLE cp_rls_off (id int)"))
        await migrator.execute(text(MIGRATION.harden_sql([supabase_like_role])))
        enabled = await migrator.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'cp_rls_off'::regclass")
        )
        await trans.rollback()
        await reader.rollback()
    assert enabled is True


async def test_hardening_reports_client_access_to_objects_it_does_not_own(supabase_like_role):
    role = supabase_like_role
    other = f"cp_other_{uuid.uuid4().hex[:8]}"
    notices: list[str] = []
    async with engine.connect() as conn:
        raw = (await conn.get_raw_connection()).driver_connection
        listener = lambda _conn, message: notices.append(message.message)  # noqa: E731
        raw.add_log_listener(listener)
        trans = await conn.begin()
        await conn.execute(text(f"CREATE ROLE {other} NOLOGIN"))
        await conn.execute(text("CREATE TABLE cp_not_ours (id int)"))
        await conn.execute(text(f"GRANT SELECT ON cp_not_ours TO {role}"))
        await conn.execute(text(f"ALTER TABLE cp_not_ours OWNER TO {other}"))
        await conn.execute(text(MIGRATION.harden_sql([role])))
        still_granted = await conn.scalar(
            text("SELECT has_table_privilege(:r, 'cp_not_ours', 'SELECT')"), {"r": role}
        )
        rls = await conn.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'cp_not_ours'::regclass")
        )
        await trans.rollback()
        raw.remove_log_listener(listener)
    assert still_granted is True and rls is False  # left alone
    assert f"skipped cp_not_ours, owned by {other}: {role} can still access it" in notices


# Routes anyone may call: sign-in flows, invitation previews, health, and
# signed-token file URLs (local storage only; the token is the credential).
PUBLIC = {
    ("GET", "/api/v1/auth/config"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password-reset"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("GET", "/api/v1/auth/invites/{token}"),
    ("POST", "/api/v1/auth/invites/accept"),
    ("GET", "/api/v1/storage/local/{token}"),
    ("PUT", "/api/v1/storage/local/{token}"),
    ("GET", "/health"),
    ("GET", "/health/live"),
}


def private_routes() -> list[tuple[str, str]]:
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if (method.upper(), path) not in PUBLIC
    ]


@pytest.mark.parametrize(("method", "path"), private_routes())
async def test_every_private_route_refuses_anonymous_callers(client, method, path):
    url = re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)
    resp = await client.request(method, url, json={})
    assert resp.status_code == 401, (method, path, resp.status_code)


async def test_internal_trigger_is_hidden_and_closed_without_its_secret(client):
    assert (await client.post("/api/v1/internal/ingest/tick")).status_code == 404
