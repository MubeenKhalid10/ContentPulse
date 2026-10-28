import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.core.ratelimit import RateLimitMiddleware
from app.db.session import SessionLocal, engine
from app.services.alignment import service as alignment
from app.services.topics import sync as topic_sync
from app.workers import scheduler, trend_tasks
from app.workers.knowledge_tasks import recover_stale_jobs
from app.workers.runner import runner


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Starting %s (%s, auth=%s, jobs=%s)",
        settings.app_name,
        settings.app_env,
        settings.auth_provider,
        settings.task_backend,
    )
    if settings.is_production and settings.frontend_url_is_local:
        logger.warning(
            "FRONTEND_URL is %s in production: invitation and password-reset emails will "
            "link there. Set FRONTEND_URL to your site's public address.",
            settings.frontend_url,
        )
    recovered = (
        await recover_stale_jobs()
        + await trend_tasks.recover_stale_runs()
        + await alignment.recover_stale_jobs()
    )
    if recovered:
        logger.warning("Marked %d interrupted background job(s) as failed", recovered)
    await trend_tasks.sync_source_registry()
    try:
        await topic_sync.backfill()
    except Exception:  # never block startup on a convenience backfill
        logger.exception("Topic backfill failed")
    scheduler_task = (
        asyncio.create_task(scheduler.scheduler_loop(), name="trend-scheduler")
        # With Celery, `celery beat` schedules instead (one scheduler per deployment).
        if settings.trend_scheduler_enabled and settings.task_backend == "inprocess"
        else None
    )
    yield
    if scheduler_task:
        scheduler_task.cancel()
    await runner.shutdown()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ContentPulse API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(RateLimitMiddleware)  # inside CORS, so 429s carry CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        """Process is up (container liveness); doesn't touch dependencies."""
        return {"status": "ok"}

    # Metrics describe the whole platform: in production they are served only
    # to a scraper holding METRICS_TOKEN, never openly.
    if settings.metrics_enabled and not (settings.is_production and not settings.metrics_token):
        from fastapi import Request
        from fastapi.responses import PlainTextResponse

        from app.ai.metrics import metrics
        from app.core.errors import Unauthorized
        from app.sources.observability import snapshot

        @app.get("/health/metrics", tags=["health"], response_class=PlainTextResponse)
        async def llm_metrics(request: Request) -> str:
            """LLM gateway and trend-source metrics (Prometheus text format).

            With METRICS_TOKEN set, scrapers must send `Authorization: Bearer
            <token>`. No organization data or credentials are ever included.
            """
            token = get_settings().metrics_token
            if token:
                import hmac

                sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
                if not hmac.compare_digest(sent.encode(), token.encode()):
                    raise Unauthorized("Metrics token required.")
            try:
                provider = await snapshot()
            except Exception:
                logger.exception("Trend source metrics snapshot failed")
                provider = ""
            return metrics.render() + provider

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Ready to serve: the database answers (load balancer health check)."""
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
