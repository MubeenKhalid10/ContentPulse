"""Provider bookkeeping during a discovery run, kept off the request path.

Every provider request writes a few small rows (budget outcome, failure
streak, the cached response). Against a distant database each write costs
about a second, and awaiting them inline made whole sources overrun their
time limit. Inside `deferring()` (one discovery run):

- those writes run in the background, at most WRITE_CONCURRENCY at a time,
  so a run never takes every connection of a small pooler; the run waits for
  them (bounded by DRAIN_SECONDS) before it reports its results;
- a provider's cooldown is read once per COOLDOWN_MEMO_SECONDS, not once per
  request, and the failure streak is cleared once per run.

Outside a run (API requests, tests, scripts) nothing changes: every write is
awaited inline and every check reads the database.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.logging import logger

WRITE_CONCURRENCY = 3
DRAIN_SECONDS = 60.0
COOLDOWN_MEMO_SECONDS = 30.0


@dataclass
class _Run:
    writes: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(WRITE_CONCURRENCY))
    pending: set[asyncio.Task] = field(default_factory=set)
    cooldowns: dict[str, tuple[float, datetime | None]] = field(default_factory=dict)
    cleared: set[str] = field(default_factory=set)


_current: ContextVar[_Run | None] = ContextVar("provider_bookkeeping", default=None)


@asynccontextmanager
async def deferring() -> AsyncIterator[None]:
    run = _Run()
    token = _current.set(run)
    try:
        yield
    finally:
        _current.reset(token)
        await _drain(run)


async def _drain(run: _Run) -> None:
    if not run.pending:
        return
    _, unfinished = await asyncio.wait(set(run.pending), timeout=DRAIN_SECONDS)
    if unfinished:
        logger.warning("%d provider bookkeeping writes still running", len(unfinished))


async def later(write: Callable[[], Awaitable[object]]) -> None:
    """Run `write` now, or in the background inside a run. Writes must handle
    their own errors (they are best effort either way)."""
    run = _current.get()
    if run is None:
        await write()
        return

    async def limited() -> None:
        async with run.writes:
            try:
                await write()
            except Exception:
                logger.warning("Provider bookkeeping write failed", exc_info=True)

    task = asyncio.create_task(limited())
    run.pending.add(task)
    task.add_done_callback(run.pending.discard)


async def cooldown(source: str, read: Callable[[], Awaitable[datetime | None]]) -> datetime | None:
    run = _current.get()
    if run is None:
        return await read()
    memo = run.cooldowns.get(source)
    if memo is not None and time.monotonic() - memo[0] < COOLDOWN_MEMO_SECONDS:
        until = memo[1]
        return until if until is not None and until > datetime.now(UTC) else None
    until = await read()
    run.cooldowns[source] = (time.monotonic(), until)
    return until


def cooldown_started(source: str, until: datetime) -> None:
    run = _current.get()
    if run is not None:
        run.cooldowns[source] = (time.monotonic(), until)
        run.cleared.discard(source)


def needs_clear(source: str) -> bool:
    """Whether the failure streak still has to be reset (once per run)."""
    run = _current.get()
    if run is None:
        return True
    if source in run.cleared:
        return False
    run.cleared.add(source)
    return True
