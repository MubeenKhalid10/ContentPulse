"""Embedding providers (spec §57). The rest of the app depends only on
`EmbeddingProvider`, never on a vendor SDK.

Embedding calls use the LLM gateway's quotas, retries and accounting
(`gate()`), but never fall back to another model: vectors from different
models can't be compared.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Protocol

import httpx

from app.ai.provider import AIError, retry_after_from
from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.models.knowledge import EMBEDDING_DIMENSIONS


class EmbeddingError(Exception):
    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class EmbeddingProvider(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddings:
    """OpenAI /v1/embeddings (also works with OpenAI-compatible gateways).
    One request per call; `gate()` adds batching limits and retries."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        batch_size: int = 64,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict = {"model": self.model, "input": texts}
        if self.model.startswith("text-embedding-3"):
            payload["dimensions"] = EMBEDDING_DIMENSIONS
        headers = {"Authorization": f"Bearer {self._api_key}"}

        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            resp = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Embedding request failed: {exc}", retryable=True) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code == 200:
            return self._parse(resp.json(), len(texts))
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise EmbeddingError(
            f"Embedding provider returned {resp.status_code}: {resp.text[:200]}",
            retryable=retryable,
            retry_after=retry_after_from(resp.headers) if retryable else None,
        )

    @staticmethod
    def _parse(body: dict, expected: int) -> list[list[float]]:
        data = sorted(body.get("data", []), key=lambda d: d["index"])
        vectors = [d["embedding"] for d in data]
        if len(vectors) != expected:
            raise EmbeddingError(
                "Embedding provider returned the wrong number of vectors.", retryable=False
            )
        if any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError(
                f"Embedding model must return {EMBEDDING_DIMENSIONS} dimensions.", retryable=False
            )
        return vectors


class GatedEmbeddings:
    """Embeddings through the LLM gateway's quotas, retries, cache and
    accounting. Wraps any `EmbeddingProvider`."""

    def __init__(self, inner: EmbeddingProvider, settings: Settings | None = None) -> None:
        self.inner = inner
        self.model = inner.model
        self.name = getattr(inner, "name", "embeddings")
        self.batch_size = max(1, getattr(inner, "batch_size", 64))
        self.settings = settings or get_settings()
        self.sleep = asyncio.sleep

    async def embed(
        self,
        texts: list[str],
        *,
        organization_id: uuid.UUID | None = None,
        workflow: str = "knowledge_embedding",
        interactive: bool = False,
    ) -> list[list[float]]:
        from app.ai import limits
        from app.ai.gateway import LLMCache, llm_cache

        cache_key = None
        if len(texts) == 1 and self.settings.llm_cache_ttl_seconds > 0:
            cache_key = LLMCache.key(
                "embedding",
                organization_id,
                self.name,
                self.model,
                hashlib.sha256(texts[0].encode()).hexdigest(),
            )
            hit = await llm_cache.get(cache_key)
            if hit is not None:
                return [hit]
        deadline = limits.monotonic() + (
            self.settings.llm_queue_timeout_interactive
            if interactive
            else self.settings.llm_queue_timeout_background
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(await self._batch(batch, organization_id, workflow, deadline))
        if cache_key:
            await llm_cache.set(cache_key, vectors[0], self.settings.llm_cache_ttl_seconds)
        return vectors

    async def _batch(
        self,
        batch: list[str],
        organization_id: uuid.UUID | None,
        workflow: str,
        deadline: float,
    ) -> list[list[float]]:
        from app.ai import limits
        from app.ai.gateway import backoff, record
        from app.ai.limits import QuotaExceeded, estimate_tokens, quota_limiter
        from app.ai.metrics import metrics

        labels = {"provider": self.name, "model": self.model, "workflow": workflow}
        call_id = uuid.uuid4()
        tokens = estimate_tokens(*batch)
        retries = 0
        while True:
            try:
                reservation = await quota_limiter.acquire(
                    self.name,
                    self.model,
                    tokens=tokens,
                    organization_id=organization_id,
                    workflow=workflow,
                    deadline=deadline,
                )
            except QuotaExceeded as exc:
                metrics.inc("llm_rate_limit_total", source="local", **labels)
                raise EmbeddingError(
                    f"Embedding quota reached: {exc.rule.label}.", retryable=not exc.rule.daily
                ) from exc
            except AIError as exc:  # the shared limiter itself is unreachable
                raise EmbeddingError(exc.message, retryable=True) from exc
            metrics.inc("llm_requests_total", **labels)
            metrics.observe("llm_queue_wait_seconds", reservation.waited, **labels)
            started_at, started = datetime.now(UTC), limits.monotonic()
            row = {
                "call_id": call_id,
                "organization_id": organization_id,
                "workflow": workflow,
                "provider": self.name,
                "model": self.model,
                "attempt": retries + 1,
                "retry_count": retries,
                "fallback_used": False,
                "queue_wait_ms": int(reservation.waited * 1000),
                "started_at": started_at,
            }
            # Providers that tell queries from documents apart get the hint.
            hint = (
                {"query": workflow == "knowledge_search"}
                if getattr(self.inner, "supports_query", False)
                else {}
            )
            try:
                vectors = await self.inner.embed(batch, **hint)
            except EmbeddingError as exc:
                elapsed = limits.monotonic() - started
                await reservation.release()
                metrics.inc("llm_requests_failed_total", error="embedding_error", **labels)
                await record(
                    **row,
                    status="failed",
                    error_kind="rate_limited_or_unavailable" if exc.retryable else "bad_request",
                    error_detail=str(exc),
                    latency_ms=int(elapsed * 1000),
                    completed_at=datetime.now(UTC),
                    usage_unavailable=True,
                )
                if not exc.retryable:
                    raise
                delay = (
                    exc.retry_after + 0.5
                    if exc.retry_after is not None
                    else backoff(retries, self.settings)
                )
                await quota_limiter.cooldown(self.name, self.model, delay)
                if (
                    retries >= self.settings.llm_max_retries
                    or delay > self.settings.llm_retry_max_delay
                    or limits.monotonic() + delay >= deadline
                ):
                    raise
                retries += 1
                metrics.inc("llm_retries_total", **labels)
                logger.warning("Embedding attempt %d failed, retrying in %.1fs", retries, delay)
                await self.sleep(delay)
                continue
            except asyncio.CancelledError:
                await reservation.release()
                raise
            elapsed = limits.monotonic() - started
            await reservation.release()
            metrics.inc("llm_requests_success_total", **labels)
            metrics.observe("llm_latency_seconds", elapsed, **labels)
            # Embedding APIs report usage inconsistently; the estimate is not
            # recorded as if it were a count.
            await record(
                **row,
                status="succeeded",
                latency_ms=int(elapsed * 1000),
                completed_at=datetime.now(UTC),
                usage_unavailable=True,
            )
            return vectors


class GeminiEmbeddings:
    """Google Gemini `batchEmbedContents` (up to 100 texts per request), at the
    database's vector size via `outputDimensionality`."""

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    MAX_BATCH = 100
    supports_query = True  # queries and documents are embedded differently

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        batch_size: int = 64,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.batch_size = min(batch_size, self.MAX_BATCH)
        self._api_key = api_key
        self._client = client

    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
        body = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task,
                    "outputDimensionality": EMBEDDING_DIMENSIONS,
                }
                for text in texts
            ]
        }
        url = f"{self.BASE_URL}/models/{self.model}:batchEmbedContents"
        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            resp = await client.post(url, json=body, headers={"x-goog-api-key": self._api_key})
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Embedding request failed: {exc}", retryable=True) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code != 200:
            try:
                payload = resp.json()
            except ValueError:
                payload = None
            retryable = resp.status_code == 429 or resp.status_code >= 500
            raise EmbeddingError(
                f"Gemini embeddings returned {resp.status_code}: {resp.text[:200]}",
                retryable=retryable,
                retry_after=retry_after_from(resp.headers, payload) if retryable else None,
            )
        vectors = [e.get("values", []) for e in resp.json().get("embeddings", [])]
        if len(vectors) != len(texts):
            raise EmbeddingError(
                "Embedding provider returned the wrong number of vectors.", retryable=False
            )
        if any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError(
                f"Embedding model must return {EMBEDDING_DIMENSIONS} dimensions.", retryable=False
            )
        return vectors


def gate(provider: EmbeddingProvider | None) -> GatedEmbeddings | None:
    """Route a provider through the gateway (idempotent)."""
    if provider is None or isinstance(provider, GatedEmbeddings):
        return provider
    return GatedEmbeddings(provider)


_override: EmbeddingProvider | None = None


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Replace the configured provider (tests, scripts)."""
    global _override
    _override = provider


def get_embedding_provider(settings: Settings | None = None) -> GatedEmbeddings | None:
    """The configured provider behind the gateway, or None when semantic
    search is not set up."""
    if _override is not None:
        return gate(_override)
    settings = settings or get_settings()
    if settings.embedding_provider == "openai" and settings.embedding_api_key:
        return gate(
            OpenAIEmbeddings(
                api_key=settings.embedding_api_key,
                model=settings.embedding_model or "text-embedding-3-small",
                base_url=settings.embedding_base_url,
                batch_size=settings.embedding_batch_size,
            )
        )
    if settings.embedding_provider == "gemini":
        from app.ai.provider import api_key_for

        key = settings.embedding_api_key or api_key_for("gemini", settings)
        if key:
            return gate(
                GeminiEmbeddings(
                    api_key=key,
                    model=settings.embedding_model or "gemini-embedding-2",
                    batch_size=settings.embedding_batch_size,
                )
            )
        logger.warning("EMBEDDING_PROVIDER=gemini needs EMBEDDING_API_KEY or GEMINI_API_KEY")
    return None


def embedding_input(title: str | None, heading: str | None, content: str) -> str:
    """Contextual embedding text: page and section names sharpen retrieval."""
    header = "\n".join(part for part in (title, heading) if part)
    return f"{header}\n\n{content}" if header else content
