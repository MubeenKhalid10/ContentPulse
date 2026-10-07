"""LLM gateway: the only path from ContentPulse to a model.

    caller -> LLMGateway.generate_structured
                -> cache (opt-in, per organization)
                -> for each model in the workflow's chain:
                       quota_limiter.acquire   (RPM, TPM, RPD, TPD, concurrency,
                                                app budgets; waits in line)
                       adapter.generate_structured   (one provider request)
                       retry transient errors with backoff / Retry-After
                   fall back to the next model only for errors another
                   model can fix (rate limits, outages, retired model,
                   daily quota)
                -> llm_requests row + metrics for every request

Callers keep using the `AIProvider` interface; `get_ai_provider()` returns
this gateway. Error handling by kind (see AIError):

    kind                retry same model   try next model   job re-queued
    rate_limited        yes (backoff)      yes              yes
    unavailable         yes (backoff)      yes              yes
    model_unavailable   no                 yes              no
    quota_exhausted     no                 yes              no
    budget_exhausted    no                 no               no
    auth / not_configured / bad_request / refused / bad_output: fail fast
"""

import asyncio
import hashlib
import json
import random
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.ai import limits
from app.ai.limits import QuotaExceeded, QuotaLimiter, estimate_tokens, quota_limiter
from app.ai.metrics import metrics
from app.ai.provider import AIError, AIErrorKind, AIProvider, StructuredResult
from app.core.config import Settings
from app.core.logging import logger

CACHE_VERSION = 1


def backoff(retry: int, settings: Settings) -> float:
    """Exponential backoff with jitter for retry number `retry` (0-based):
    base x 2^retry, capped, then a random point in its upper half."""
    ceiling = min(settings.llm_retry_max_delay, settings.llm_retry_base_delay * 2**retry)
    return random.uniform(ceiling / 2, ceiling)


# --- Cache -------------------------------------------------------------------------


class LLMCache:
    """Results of repeatable calls, keyed per organization: one organization
    can never read another's entries. The key hashes everything that shapes
    the answer (models, prompts incl. organization context and knowledge
    passages, schema), so a change to any of them is a miss."""

    MAX_MEMORY_ENTRIES = 2000

    def __init__(self) -> None:
        self.memory: dict[str, tuple[float, str]] = {}

    def clear(self) -> None:
        self.memory.clear()

    @staticmethod
    def key(namespace: str, organization_id: uuid.UUID | None, *parts: Any) -> str:
        digest = hashlib.sha256(
            json.dumps([CACHE_VERSION, *parts], sort_keys=True, default=str).encode()
        ).hexdigest()
        return f"cp:llm:cache:{namespace}:{organization_id or 'global'}:{digest}"

    def _redis(self):
        backend = quota_limiter.backend()
        return getattr(backend, "client", None)

    async def get(self, key: str) -> Any | None:
        try:
            client = self._redis()
            if client is not None:
                raw = await client.get(key)
                return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("LLM cache read failed: %s", exc)
            return None
        entry = self.memory.get(key)
        if entry and entry[0] > time.monotonic():
            return json.loads(entry[1])
        self.memory.pop(key, None)
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        raw = json.dumps(value)
        try:
            client = self._redis()
            if client is not None:
                await client.set(key, raw, ex=ttl)
                return
        except Exception as exc:
            logger.warning("LLM cache write failed: %s", exc)
            return
        if len(self.memory) >= self.MAX_MEMORY_ENTRIES:
            now = time.monotonic()
            self.memory = {k: v for k, v in self.memory.items() if v[0] > now}
            if len(self.memory) >= self.MAX_MEMORY_ENTRIES:
                self.memory.pop(next(iter(self.memory)))
        self.memory[key] = (time.monotonic() + ttl, raw)


llm_cache = LLMCache()


# --- Accounting --------------------------------------------------------------------


async def record(**row: Any) -> None:
    """Persist one llm_requests row. Never fails the call it describes."""
    from app.db.session import SessionLocal
    from app.models.ai import LLMRequest

    detail = row.get("error_detail")
    if detail:
        row["error_detail"] = str(detail)[:300]
    try:
        async with SessionLocal() as db:
            db.add(LLMRequest(**row))
            await db.commit()
    except Exception as exc:
        logger.warning("Could not record LLM request: %s", exc)
    logger.info(
        "llm_request workflow=%s provider=%s model=%s status=%s error=%s attempt=%s "
        "wait_ms=%s latency_ms=%s tokens=%s/%s fallback=%s",
        row.get("workflow"),
        row.get("provider"),
        row.get("model"),
        row.get("status"),
        row.get("error_kind"),
        row.get("attempt"),
        row.get("queue_wait_ms"),
        row.get("latency_ms"),
        row.get("input_tokens"),
        row.get("output_tokens"),
        row.get("fallback_used"),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _total(a: int | None, b: int | None) -> int | None:
    return None if a is None and b is None else (a or 0) + (b or 0)


# --- Gateway -----------------------------------------------------------------------


class LLMGateway:
    """Rate-limited, retried, recorded access to a chain of models."""

    def __init__(
        self,
        adapters: list[AIProvider],
        settings: Settings,
        limiter: QuotaLimiter | None = None,
    ) -> None:
        assert adapters, "the gateway needs at least one model"
        self.adapters = adapters
        self.settings = settings
        self.limiter = limiter or quota_limiter
        self.sleep = asyncio.sleep

    @property
    def name(self) -> str:
        return self.adapters[0].name

    @property
    def model(self) -> str:
        return self.adapters[0].model

    @property
    def chain(self) -> list[str]:
        return [f"{a.name}/{a.model}" for a in self.adapters]

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
        workflow: str = "default",
        organization_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        interactive: bool = False,
        cache: bool = False,
    ) -> StructuredResult:
        """One structured answer. `interactive` calls (someone is waiting on
        the response) give up queueing sooner; `cache` reuses an identical
        earlier answer for this organization."""
        settings = self.settings
        call_id = uuid.uuid4()
        base = {
            "call_id": call_id,
            "job_id": job_id,
            "workflow": workflow,
            "organization_id": organization_id,
        }

        cache_key = None
        if cache and settings.llm_cache_ttl_seconds > 0:
            cache_key = LLMCache.key(
                workflow, organization_id, self.chain, system, prompt, schema, max_tokens
            )
            hit = await llm_cache.get(cache_key)
            if hit is not None:
                metrics.inc("llm_cache_hits_total", workflow=workflow)
                now = _now()
                await record(
                    **base,
                    provider=hit["provider"],
                    model=hit["model"],
                    status="cached",
                    attempt=0,
                    retry_count=0,
                    fallback_used=False,
                    queue_wait_ms=0,
                    latency_ms=0,
                    started_at=now,
                    completed_at=now,
                    usage_unavailable=True,
                )
                return StructuredResult(
                    data=hit["data"],
                    model=hit["model"],
                    input_tokens=None,
                    output_tokens=None,
                    provider=hit["provider"],
                    cached=True,
                    attempts=0,
                )

        timeout = (
            settings.llm_queue_timeout_interactive
            if interactive
            else settings.llm_queue_timeout_background
        )
        deadline = limits.monotonic() + timeout
        input_tokens = estimate_tokens(system, prompt, json.dumps(schema))
        attempt = 0
        last_error: AIError | None = None

        for index, adapter in enumerate(self.adapters):
            fallback_used = index > 0
            if fallback_used:
                assert last_error is not None
                logger.warning(
                    "%s: %s/%s failed (%s); falling back to %s/%s",
                    workflow,
                    self.adapters[index - 1].name,
                    self.adapters[index - 1].model,
                    last_error.kind.value,
                    adapter.name,
                    adapter.model,
                )
            labels = {"provider": adapter.name, "model": adapter.model, "workflow": workflow}
            cap = self.limiter.catalog.model(adapter.name, adapter.model).max_output_tokens
            output_tokens = min(max_tokens, cap) if cap else max_tokens
            # Reserve the input estimate plus the output allowance (providers
            # count it); corrected to the reported total after the call.
            tokens = input_tokens + output_tokens
            retries = 0
            while True:
                # Split the remaining queue time between this model and the
                # ones after it, so a saturated primary still leaves room to
                # fall back before the deadline.
                remaining = max(0.0, deadline - limits.monotonic())
                model_deadline = limits.monotonic() + remaining / (len(self.adapters) - index)
                try:
                    reservation = await self.limiter.acquire(
                        adapter.name,
                        adapter.model,
                        tokens=tokens,
                        organization_id=organization_id,
                        workflow=workflow,
                        deadline=model_deadline,
                    )
                except QuotaExceeded as exc:
                    metrics.inc("llm_rate_limit_total", source="local", **labels)
                    if exc.rule.scope == "budget":
                        raise AIError(
                            AIErrorKind.BUDGET_EXHAUSTED, f"AI budget reached: {exc.rule.label}."
                        ) from exc
                    kind = (
                        AIErrorKind.QUOTA_EXHAUSTED if exc.rule.daily else AIErrorKind.RATE_LIMITED
                    )
                    last_error = AIError(
                        kind, f"Local limit reached: {exc.rule.label}.", retry_after=exc.wait
                    )
                    logger.warning("%s: %s", workflow, last_error.message)
                    break  # next model, if any

                attempt += 1
                waited = reservation.waited
                metrics.observe("llm_queue_wait_seconds", waited, **labels)
                metrics.inc("llm_requests_total", **labels)
                metrics.gauge("llm_concurrency", 1, provider=adapter.name, model=adapter.model)
                started_at, started = _now(), limits.monotonic()
                row = {
                    **base,
                    "provider": adapter.name,
                    "model": adapter.model,
                    "attempt": attempt,
                    "retry_count": retries,
                    "fallback_used": fallback_used,
                    "queue_wait_ms": int(waited * 1000),
                    "started_at": started_at,
                }
                try:
                    result = await adapter.generate_structured(
                        system=system, prompt=prompt, schema=schema, max_tokens=output_tokens
                    )
                except AIError as exc:
                    elapsed = limits.monotonic() - started
                    await reservation.release()
                    metrics.gauge("llm_concurrency", -1, provider=adapter.name, model=adapter.model)
                    metrics.observe("llm_latency_seconds", elapsed, **labels)
                    metrics.inc("llm_requests_failed_total", error=exc.kind.value, **labels)
                    if exc.kind == AIErrorKind.RATE_LIMITED:
                        metrics.inc("llm_rate_limit_total", source="provider", **labels)
                    await record(
                        **row,
                        status="failed",
                        error_kind=exc.kind.value,
                        error_detail=exc.message,
                        latency_ms=int(elapsed * 1000),
                        completed_at=_now(),
                        usage_unavailable=True,
                    )
                    last_error = exc
                    if exc.retryable:
                        delay = (
                            exc.retry_after + random.uniform(0, 1)
                            if exc.retry_after is not None
                            else backoff(retries, settings)
                        )
                        # Every process pauses this model, not just this call.
                        await self.limiter.cooldown(adapter.name, adapter.model, delay)
                        if (
                            retries < settings.llm_max_retries
                            and delay <= settings.llm_retry_max_delay
                            and limits.monotonic() + delay < deadline
                        ):
                            retries += 1
                            metrics.inc("llm_retries_total", **labels)
                            logger.warning(
                                "%s: %s/%s %s; retry %d in %.1fs",
                                workflow,
                                adapter.name,
                                adapter.model,
                                exc.kind.value,
                                retries,
                                delay,
                            )
                            await self.sleep(delay)
                            continue
                    elif exc.try_fallback:
                        # A retired model or spent daily quota: let other calls
                        # skip it for a while instead of finding out again.
                        await self.limiter.cooldown(adapter.name, adapter.model, 600)
                    if exc.try_fallback and settings.llm_fallback_enabled:
                        break  # next model, if any
                    raise
                except asyncio.CancelledError:
                    await reservation.release()
                    metrics.gauge("llm_concurrency", -1, provider=adapter.name, model=adapter.model)
                    raise
                except Exception as exc:
                    # An application bug, not a provider failure: no retry,
                    # no fallback (it would fail the same way everywhere).
                    elapsed = limits.monotonic() - started
                    await reservation.release()
                    metrics.gauge("llm_concurrency", -1, provider=adapter.name, model=adapter.model)
                    metrics.inc("llm_requests_failed_total", error="application_error", **labels)
                    await record(
                        **row,
                        status="failed",
                        error_kind="application_error",
                        error_detail=type(exc).__name__,
                        latency_ms=int(elapsed * 1000),
                        completed_at=_now(),
                        usage_unavailable=True,
                    )
                    raise

                elapsed = limits.monotonic() - started
                total = _total(result.input_tokens, result.output_tokens)
                await reservation.release(total)
                metrics.gauge("llm_concurrency", -1, provider=adapter.name, model=adapter.model)
                metrics.observe("llm_latency_seconds", elapsed, **labels)
                metrics.inc("llm_requests_success_total", **labels)
                if result.input_tokens:
                    metrics.inc("llm_input_tokens_total", result.input_tokens, **labels)
                if result.output_tokens:
                    metrics.inc("llm_output_tokens_total", result.output_tokens, **labels)
                if fallback_used:
                    metrics.inc("llm_fallback_total", **labels)
                await record(
                    **row,
                    status="succeeded",
                    latency_ms=int(elapsed * 1000),
                    completed_at=_now(),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    total_tokens=total,
                    usage_unavailable=total is None,
                )
                result.provider = adapter.name
                result.attempts = attempt
                result.fallback_used = fallback_used
                if cache_key:
                    await llm_cache.set(
                        cache_key,
                        {"data": result.data, "model": result.model, "provider": adapter.name},
                        settings.llm_cache_ttl_seconds,
                    )
                return result

        assert last_error is not None
        if len(self.adapters) > 1:
            raise AIError(
                last_error.kind,
                f"All configured AI models failed; last: {last_error.message}",
                retry_after=last_error.retry_after,
            ) from last_error
        raise last_error
