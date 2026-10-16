"""The shared provider tables are backend-only: RLS without policies, client
privileges revoked, no API route, and stored copies removed when a provider
may no longer be stored."""

import importlib
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.models.provider import ProviderCache, ProviderUsage
from app.services.housekeeping import run_housekeeping

TABLES = ("provider_cache", "provider_usage", "instagram_hashtag_usage")
MIGRATION = importlib.import_module(
    "app.db.migrations.versions.20261014_b4d7f0a5e163_backend_only_provider_tables"
)


@pytest.fixture
async def probe_role():
    """A throwaway role standing in for Supabase's `anon`/`authenticated`,
    with the table grants Supabase gives those roles by default."""
    name = f"cp_probe_{uuid.uuid4().hex[:8]}"
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {name} NOLOGIN"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {name}"))
        for table in TABLES:
            await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {name}"))
    try:
        yield name
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP OWNED BY {name}"))
            await conn.execute(text(f"DROP ROLE {name}"))


async def test_rls_is_on_without_policies_and_not_forced():
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:tables)"
            ),
            {"tables": list(TABLES)},
        )
        state = {name: (rls, forced) for name, rls, forced in rows}
        policies = await conn.scalar(
            text("SELECT count(*) FROM pg_policies WHERE tablename = ANY(:tables)"),
            {"tables": list(TABLES)},
        )
    assert state == {t: (True, False) for t in TABLES}
    assert policies == 0


async def test_enabling_rls_skips_tables_that_have_it_without_locking_them():
    # Production already has RLS on these tables: the migration must not queue
    # for an ACCESS EXCLUSIVE lock behind live readers, but must still turn RLS
    # on where it is off.
    async with engine.connect() as reader, engine.connect() as migrator:
        await reader.begin()
        await reader.execute(text("LOCK TABLE provider_cache IN ACCESS SHARE MODE"))
        trans = await migrator.begin()
        await migrator.execute(text("ALTER TABLE provider_usage DISABLE ROW LEVEL SECURITY"))
        await migrator.execute(text("SET LOCAL lock_timeout = '1s'"))
        await migrator.execute(text(MIGRATION.enable_rls_sql(TABLES)))
        await migrator.execute(text(MIGRATION.enable_rls_sql(TABLES)))  # idempotent
        rows = await migrator.execute(
            text("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:tables)"),
            {"tables": list(TABLES)},
        )
        state = dict(rows.all())
        await trans.rollback()
        await reader.rollback()
    assert state == {t: True for t in TABLES}


async def test_client_roles_see_and_write_nothing_even_with_grants(db, probe_role):
    db.add(ProviderCache(key="a" * 64, source="google_trends", body=b"x"))
    db.add(ProviderUsage(source="gnews", usage_date=datetime.now(UTC).date(), scope="*"))
    await db.commit()
    async with engine.connect() as conn:
        await conn.execute(text(f"SET ROLE {probe_role}"))
        for table in TABLES:
            assert await conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        with pytest.raises(Exception, match="row-level security"):
            await conn.execute(
                text("INSERT INTO provider_cache (key, source) VALUES (:k, 'x')"), {"k": "b" * 64}
            )
        await conn.rollback()
    # The backend role (the tables' owner) is unaffected.
    assert await db.scalar(text("SELECT count(*) FROM provider_cache")) == 1


async def test_migration_revokes_client_privileges(probe_role):
    async with engine.begin() as conn:
        await conn.execute(text(MIGRATION.revoke_sql(TABLES, [probe_role])))
        for table in TABLES:
            allowed = await conn.scalar(
                text("SELECT has_table_privilege(:role, :table, 'SELECT')"),
                {"role": probe_role, "table": table},
            )
            assert allowed is False
    # Roles that don't exist (no Supabase locally) are skipped, not an error.
    async with engine.begin() as conn:
        await conn.execute(text(MIGRATION.revoke_sql(TABLES, ["no_such_role_xyz"])))


def test_no_api_route_reads_provider_tables():
    api = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    for path in api.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in ("ProviderCache", "ProviderUsage", "InstagramHashtagUse", "provider_cache"):
            assert name not in source, f"{path.name} references {name}"


async def test_providers_no_longer_allowed_lose_their_stored_copies(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "provider_cache_backend", "postgres")
    monkeypatch.setattr(settings, "provider_cache_persist_sources", ["google_trends", "reddit"])
    fresh = datetime.now(UTC) + timedelta(hours=1)
    for source in ("google_trends", "newsdata", "reddit"):
        db.add(ProviderCache(key=source.ljust(64, "0"), source=source, body=b"x", expires_at=fresh))
    await db.commit()
    result = await run_housekeeping()
    # newsdata isn't listed; reddit is listed but may never be stored.
    assert result["provider_cache"] == 2
    left = (await db.execute(text("SELECT source FROM provider_cache"))).scalars().all()
    assert left == ["google_trends"]

    monkeypatch.setattr(settings, "provider_cache_backend", "memory")  # switched back
    assert (await run_housekeeping())["provider_cache"] == 1


async def test_models_match_the_migrations():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    def diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn)
        return compare_metadata(ctx, Base.metadata)

    async with engine.connect() as conn:
        changes = await conn.run_sync(diff)
    ours = {*TABLES, "trend_sources", "trend_discovery_runs", "organization_settings"}

    # Compare only what this work added or changed (other tables are out of scope).
    relevant = [c for c in changes if any(f"'{t}'" in repr(c) for t in ours)]
    assert relevant == [], relevant
