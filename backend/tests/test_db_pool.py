"""Connections are only pinged after sitting idle, and a dead one is replaced."""

import asyncpg
from sqlalchemy import text

from app.db import session
from app.db.session import SessionLocal, engine
from tests.conftest import TEST_DATABASE_URL


async def test_idle_connection_is_pinged_and_still_works(monkeypatch):
    monkeypatch.setattr(session, "IDLE_PING_AFTER", 0.0)  # every reuse counts as idle
    for _ in range(3):
        async with SessionLocal() as s:
            assert (await s.execute(text("SELECT 1"))).scalar() == 1


async def test_a_dead_idle_connection_is_replaced(monkeypatch):
    monkeypatch.setattr(session, "IDLE_PING_AFTER", 0.0)
    async with SessionLocal() as s:  # leaves one connection idle in the pool
        pid = (await s.execute(text("SELECT pg_backend_pid()"))).scalar()
    # Kill it on the server, as an idle timeout at the database or pooler would.
    admin = await asyncpg.connect(TEST_DATABASE_URL.replace("+asyncpg", ""))
    try:
        await admin.execute(f"SELECT pg_terminate_backend({int(pid)})")
    finally:
        await admin.close()
    # Check out every pooled connection at once so the dead one is certainly met
    # (and replaced) here, not by a later test.
    held = [await engine.connect() for _ in range(engine.pool.size())]
    try:
        for connection in held:
            assert (await connection.execute(text("SELECT 1"))).scalar() == 1
            assert (await connection.execute(text("SELECT pg_backend_pid()"))).scalar() != pid
    finally:
        for connection in held:
            await connection.close()


async def test_pool_does_not_ping_on_every_checkout():
    assert engine.pool._pre_ping is False
