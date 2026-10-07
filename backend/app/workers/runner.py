"""In-process background job runner.

Long-running work (crawls, re-indexing) must never block a request (spec rule
6). Until Celery arrives in Sprint 9, jobs run as asyncio tasks in the API
process. Job state lives in the database, so swapping this runner for a Celery
queue only changes `submit`.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logging import logger


class JobRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def submit(self, coro: Coroutine[Any, Any, None], *, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("Background job %s crashed", task.get_name(), exc_info=task.exception())

    async def wait_idle(self) -> None:
        """Wait for all submitted jobs (tests, graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)


runner = JobRunner()
