import time
from collections.abc import AsyncIterator

from sqlalchemy import event, exc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.url import async_database_url

_url, _connect_args = async_database_url(get_settings().database_url)
# `pool_pre_ping` would add a full round trip to the database to every request,
# which is slow when the database is far away. Instead a connection is checked
# only after it sat idle long enough for the server or pooler to have dropped it.
engine = create_async_engine(_url, connect_args=_connect_args, pool_recycle=1800)
IDLE_PING_AFTER = 30.0  # seconds


@event.listens_for(engine.sync_engine, "checkin")
def _note_idle_start(_dbapi_connection, connection_record) -> None:
    connection_record.info["idle_since"] = time.monotonic()


@event.listens_for(engine.sync_engine, "checkout")
def _ping_if_idle(dbapi_connection, connection_record, _connection_proxy) -> None:
    idle_since = connection_record.info.get("idle_since")
    if idle_since is None or time.monotonic() - idle_since < IDLE_PING_AFTER:
        return
    try:
        engine.sync_engine.dialect.do_ping(dbapi_connection)
    except Exception as error:  # the pool replaces the connection and retries
        raise exc.DisconnectionError("Idle connection is no longer usable.") from error


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
