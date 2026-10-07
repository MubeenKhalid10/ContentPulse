"""LLM provider adapters (spec §57).

The application depends only on `AIProvider.generate_structured` and the
`AIError` kinds. Each adapter makes exactly one request and translates its
vendor's errors into those kinds; rate limiting, retries, fallback, caching
and accounting all live in `app.ai.gateway`, which `get_ai_provider` returns.
Structured output is schema-enforced by the API, then re-validated by the
caller (spec §26: never parse free-form LLM prose).
"""

import json
import os
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import StrEnum
from time import time
from typing import TYPE_CHECKING, Any, Protocol

import anthropic
import httpx

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.ai.gateway import LLMGateway


class AIErrorKind(StrEnum):
    NOT_CONFIGURED = "not_configured"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    REFUSED = "refused"
    BAD_OUTPUT = "bad_output"
    BAD_REQUEST = "bad_request"
    # The configured model doesn't exist or was retired for this key.
    MODEL_UNAVAILABLE = "model_unavailable"
    # A model's daily quota is used up (the provider's, or our share of it).
    QUOTA_EXHAUSTED = "quota_exhausted"
    # The application's own daily AI budget is used up.
    BUDGET_EXHAUSTED = "budget_exhausted"
    # Too big for this model: the prompt exceeds its context or per-request
    # token limit, or the answer was cut off at its output cap.
    OVERSIZED = "oversized"


# What people see. Provider names and raw errors stay in logs and llm_requests.
USER_MESSAGES = {
    AIErrorKind.RATE_LIMITED: (
        "AI processing is temporarily unavailable. No data was lost. Please try again shortly."
    ),
    AIErrorKind.UNAVAILABLE: (
        "AI processing is temporarily unavailable. No data was lost. Please try again shortly."
    ),
    AIErrorKind.QUOTA_EXHAUSTED: (
        "AI processing capacity for today has been reached. Please try again later."
    ),
    AIErrorKind.BUDGET_EXHAUSTED: (
        "AI processing capacity for today has been reached. Please try again later."
    ),
    AIErrorKind.AUTH: "AI processing isn't set up correctly. Ask an administrator to check it.",
    AIErrorKind.NOT_CONFIGURED: (
        "AI processing isn't set up correctly. Ask an administrator to check it."
    ),
    AIErrorKind.MODEL_UNAVAILABLE: (
        "AI processing isn't set up correctly. Ask an administrator to check it."
    ),
    AIErrorKind.REFUSED: "The AI declined this request. Try rewording it.",
    AIErrorKind.BAD_OUTPUT: "The AI returned an unusable answer. Please try again.",
    AIErrorKind.BAD_REQUEST: "The AI couldn't process this request. Please try again.",
    AIErrorKind.OVERSIZED: "The AI couldn't complete this request. Please try again.",
}
QUEUED_MESSAGE = (
    "The AI service is temporarily busy. Your request has been queued and will retry automatically."
)


class AIError(Exception):
    """`message` is the internal detail; `user_message` is safe to show.

    `public=True` marks a message written for people (e.g. "The post no longer
    exists."), shown as is.
    """

    def __init__(
        self,
        kind: AIErrorKind,
        message: str,
        *,
        retry_after: float | None = None,
        public: bool = False,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after
        self.public = public

    @property
    def retryable(self) -> bool:
        """The same request may succeed later on the same model."""
        return self.kind in (AIErrorKind.RATE_LIMITED, AIErrorKind.UNAVAILABLE)

    @property
    def try_fallback(self) -> bool:
        """Another model may succeed where this one failed. Never for bad keys,
        bad requests or bad output: those would only burn other quotas."""
        return self.retryable or self.kind in (
            AIErrorKind.MODEL_UNAVAILABLE,
            AIErrorKind.QUOTA_EXHAUSTED,
            AIErrorKind.OVERSIZED,
        )

    @property
    def user_message(self) -> str:
        return self.message if self.public else USER_MESSAGES[self.kind]


@dataclass
class StructuredResult:
    data: dict[str, Any]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    # Filled in by the gateway.
    provider: str = ""
    cached: bool = False
    attempts: int = 1
    fallback_used: bool = False


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> StructuredResult: ...


# --- Retry-After --------------------------------------------------------------------

_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


def retry_after_from(headers: httpx.Headers | dict | None, body: Any = None) -> float | None:
    """Seconds the provider asked us to wait, from `retry-after(-ms)` headers or
    a Google `RetryInfo.retryDelay` ("17s") in the error body. None if absent."""
    if headers:
        ms = headers.get("retry-after-ms")
        if ms:
            try:
                return max(0.0, float(ms) / 1000)
            except ValueError:
                pass
        value = headers.get("retry-after")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(0.0, parsedate_to_datetime(value).timestamp() - time())
                except (TypeError, ValueError):
                    pass
    if isinstance(body, dict):
        for detail in (body.get("error") or {}).get("details") or []:
            match = _DURATION.match(str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


_TOO_LARGE = re.compile(
    r"too large|too long|context.length|maximum context|reduce the length|exceeds the maximum",
    re.IGNORECASE,
)


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


# --- Anthropic ---------------------------------------------------------------------


def _map_anthropic_error(exc: Exception) -> AIError:
    response = getattr(exc, "response", None)
    retry_after = retry_after_from(response.headers) if response is not None else None
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return AIError(AIErrorKind.AUTH, "Anthropic rejected the API key.")
    if isinstance(exc, anthropic.RateLimitError):
        return AIError(
            AIErrorKind.RATE_LIMITED,
            "Anthropic is rate limiting requests.",
            retry_after=retry_after,
        )
    if isinstance(exc, anthropic.NotFoundError):
        return AIError(AIErrorKind.MODEL_UNAVAILABLE, f"Anthropic model unavailable: {exc.message}")
    if isinstance(exc, anthropic.BadRequestError):
        if _TOO_LARGE.search(exc.message):
            return AIError(AIErrorKind.OVERSIZED, f"Too large for Anthropic: {exc.message}")
        return AIError(AIErrorKind.BAD_REQUEST, f"Anthropic rejected the request: {exc.message}")
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 413:
        return AIError(AIErrorKind.OVERSIZED, "Request too large for Anthropic.")
    if isinstance(exc, anthropic.APIStatusError):
        return AIError(
            AIErrorKind.UNAVAILABLE,
            f"Anthropic error ({exc.status_code}).",
            retry_after=retry_after,
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError(AIErrorKind.UNAVAILABLE, "Could not reach Anthropic.")
    return AIError(AIErrorKind.UNAVAILABLE, f"Anthropic request failed: {type(exc).__name__}")


class AnthropicProvider:
    """Claude via the official SDK (`anthropic`)."""

    name = "anthropic"
    # The "default" fallback routes a refusal to Anthropic's recommended
    # substitute model server-side, inside the same request.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(
        self,
        *,
        model: str,
        effort: str,
        api_key: str | None,
        timeout: float,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        # api_key=None lets the SDK resolve ANTHROPIC_API_KEY / an auth profile.
        # The gateway owns retries: the SDK must not add hidden ones.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=0
        )

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> StructuredResult:
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                betas=[self.FALLBACK_BETA],
                fallbacks="default",
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                # The system prompt is identical across trends for one
                # organization: cache it.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise _map_anthropic_error(exc) from exc

        if response.stop_reason == "refusal":
            category = (
                getattr(response.stop_details, "category", None) if response.stop_details else None
            )
            raise AIError(
                AIErrorKind.REFUSED,
                f"The model declined this request{f' ({category})' if category else ''}.",
            )
        if response.stop_reason == "max_tokens":
            raise AIError(AIErrorKind.OVERSIZED, "The AI response was cut off (max_tokens).")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no content.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned invalid JSON.") from exc
        usage = response.usage
        return StructuredResult(
            data=data,
            model=response.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


# --- Gemini ------------------------------------------------------------------------

REFUSAL_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
)


class GeminiProvider:
    """Google Gemini via the REST `generateContent` API (JSON-schema output).

    Called over HTTP with httpx rather than the google-genai SDK: only one
    endpoint is needed, and it avoids pinning extra dependencies.
    """

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = client

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.BASE_URL}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self._api_key}
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach Gemini ({type(exc).__name__})."
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code == 200:
            return resp.json()
        raise self._error(resp)

    @staticmethod
    def _error(resp: httpx.Response) -> AIError:
        body = _json(resp)
        error = (body or {}).get("error", {}) if isinstance(body, dict) else {}
        detail = str(error.get("message") or resp.text[:200])
        lowered = detail.lower()
        retry_after = retry_after_from(resp.headers, body)
        if resp.status_code in (401, 403):
            return AIError(AIErrorKind.AUTH, "Gemini rejected the API key.")
        if resp.status_code == 429:
            # Per-day quotas don't come back in seconds: try another model.
            quota_ids = " ".join(
                str(v.get("quotaId", ""))
                for d in error.get("details") or []
                for v in d.get("violations") or []
            )
            if "PerDay" in quota_ids:
                return AIError(AIErrorKind.QUOTA_EXHAUSTED, "Gemini daily quota exhausted.")
            return AIError(
                AIErrorKind.RATE_LIMITED, "Gemini rate limit reached.", retry_after=retry_after
            )
        if resp.status_code >= 500:
            return AIError(
                AIErrorKind.UNAVAILABLE,
                f"Gemini error ({resp.status_code}).",
                retry_after=retry_after,
            )
        if resp.status_code == 400 and "api key" in lowered:
            return AIError(AIErrorKind.AUTH, "Gemini rejected the API key.")
        if resp.status_code == 413 or _TOO_LARGE.search(detail):
            return AIError(AIErrorKind.OVERSIZED, f"Too large for Gemini: {detail[:200]}")
        if resp.status_code == 404 or "no longer available" in lowered or "not found" in lowered:
            return AIError(
                AIErrorKind.MODEL_UNAVAILABLE, f"Gemini model unavailable: {detail[:200]}"
            )
        return AIError(AIErrorKind.BAD_REQUEST, f"Gemini rejected the request: {detail[:200]}")

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> StructuredResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": max_tokens,
            },
        }
        data = await self._post(body)
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise AIError(AIErrorKind.REFUSED, f"Gemini blocked the request ({block}).")
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIError(AIErrorKind.BAD_OUTPUT, "Gemini returned no candidates.")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish in REFUSAL_FINISH_REASONS:
            raise AIError(AIErrorKind.REFUSED, f"Gemini declined to answer ({finish}).")
        if finish == "MAX_TOKENS":
            raise AIError(AIErrorKind.OVERSIZED, "The AI response was cut off (max tokens).")
        text = "".join(
            part.get("text", "")
            for part in (candidate.get("content") or {}).get("parts", [])
            if not part.get("thought")
        )
        if not text.strip():
            raise AIError(AIErrorKind.BAD_OUTPUT, "Gemini returned no content.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(AIErrorKind.BAD_OUTPUT, "Gemini returned invalid JSON.") from exc
        usage = data.get("usageMetadata") or {}
        output = usage.get("candidatesTokenCount")
        if output is not None and usage.get("thoughtsTokenCount"):
            output += usage["thoughtsTokenCount"]  # billed and rate limited as output
        return StructuredResult(
            data=parsed,
            model=data.get("modelVersion") or self.model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=output,
        )


# --- OpenAI-compatible (OpenAI, Groq, Cerebras, OpenRouter) ------------------------


class OpenAICompatibleProvider:
    """Any `/chat/completions` API with JSON-schema `response_format`."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout
        self._client = client

    def _error(self, resp: httpx.Response) -> AIError:
        body = _json(resp)
        error = body.get("error") if isinstance(body, dict) else None
        error = error if isinstance(error, dict) else {}
        detail = str(error.get("message") or resp.text[:200])
        code = str(error.get("code") or error.get("type") or "")
        retry_after = retry_after_from(resp.headers, body)
        label = self.name.capitalize()
        if resp.status_code in (401, 403):
            return AIError(AIErrorKind.AUTH, f"{label} rejected the API key.")
        if resp.status_code == 429:
            if code == "insufficient_quota":  # billing, not a rate: won't clear soon
                return AIError(AIErrorKind.QUOTA_EXHAUSTED, f"{label} quota exhausted.")
            return AIError(
                AIErrorKind.RATE_LIMITED, f"{label} rate limit reached.", retry_after=retry_after
            )
        if resp.status_code >= 500:
            return AIError(
                AIErrorKind.UNAVAILABLE,
                f"{label} error ({resp.status_code}).",
                retry_after=retry_after,
            )
        if (
            resp.status_code == 413
            or code == "context_length_exceeded"
            or _TOO_LARGE.search(detail)
        ):
            # Groq counts max_tokens against its per-minute token limit, so a
            # big request can never fit there: let a roomier model take it.
            return AIError(AIErrorKind.OVERSIZED, f"Too large for {label}: {detail[:200]}")
        if resp.status_code == 404 or code == "model_not_found":
            return AIError(
                AIErrorKind.MODEL_UNAVAILABLE, f"{label} model unavailable: {detail[:200]}"
            )
        return AIError(AIErrorKind.BAD_REQUEST, f"{label} rejected the request: {detail[:200]}")

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> StructuredResult:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema},
            },
        }
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach {self.name} ({type(exc).__name__})."
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code != 200:
            raise self._error(resp)
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no choices.")
        choice = choices[0]
        message = choice.get("message") or {}
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise AIError(AIErrorKind.REFUSED, "The model declined this request.")
        if choice.get("finish_reason") == "length":
            raise AIError(AIErrorKind.OVERSIZED, "The AI response was cut off (max tokens).")
        text = message.get("content") or ""
        if not text.strip():
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no content.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned invalid JSON.") from exc
        usage = data.get("usage") or {}
        return StructuredResult(
            data=parsed,
            model=data.get("model") or self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


# --- Configuration -----------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    # (default model, same-provider fallback); None = LLM_MODEL is required.
    default_models: tuple[str, str] | None
    key_env_vars: tuple[str, ...]
    base_url: str | None = None  # OpenAI-compatible providers


PROVIDERS: dict[str, ProviderSpec] = {
    # The Gemini fallback is the previous Flash: it has roomier free-tier quotas.
    "gemini": ProviderSpec(
        ("gemini-3.8-flash", "gemini-3.5-flash"), ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    ),
    "anthropic": ProviderSpec(
        ("claude-opus-5-5", "claude-opus-5"), ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    ),
    "openai": ProviderSpec(None, ("OPENAI_API_KEY",), "https://api.openai.com/v1"),
    "groq": ProviderSpec(
        ("openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
        ("GROQ_API_KEY",),
        "https://api.groq.com/openai/v1",
    ),
    "cerebras": ProviderSpec(
        ("gpt-oss-120b", "qwen-3.8-27b"), ("CEREBRAS_API_KEY",), "https://api.cerebras.ai/v1"
    ),
    "openrouter": ProviderSpec(None, ("OPENROUTER_API_KEY",), "https://openrouter.ai/api/v1"),
}


@dataclass(frozen=True)
class LLMTarget:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> "LLMTarget | None":
        """ "provider/model" (the model may itself contain slashes)."""
        provider, _, model = value.strip().partition("/")
        return cls(provider, model) if provider and model else None

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


def api_key_for(provider: str, settings: Settings) -> str | None:
    if provider == settings.llm_provider and settings.llm_api_key:
        return settings.llm_api_key
    configured = getattr(settings, f"{provider}_api_key", None)
    if configured:
        return configured
    spec = PROVIDERS.get(provider)
    for name in spec.key_env_vars if spec else ():
        if os.environ.get(name):
            return os.environ[name]
    return None


def build_adapter(target: LLMTarget, settings: Settings) -> AIProvider:
    key = api_key_for(target.provider, settings)
    if target.provider == "gemini":
        return GeminiProvider(
            model=target.model, api_key=key or "", timeout=settings.llm_timeout_seconds
        )
    if target.provider == "anthropic":
        return AnthropicProvider(
            model=target.model,
            effort=settings.llm_effort,
            api_key=key,
            timeout=settings.llm_timeout_seconds,
        )
    spec = PROVIDERS[target.provider]
    return OpenAICompatibleProvider(
        name=target.provider,
        model=target.model,
        api_key=key or "",
        base_url=settings.llm_base_urls.get(target.provider) or spec.base_url or "",
        timeout=settings.llm_timeout_seconds,
    )


def _usable(target: LLMTarget, settings: Settings) -> bool:
    return target.provider in PROVIDERS and api_key_for(target.provider, settings) is not None


def primary_targets(settings: Settings) -> list[LLMTarget]:
    """LLM_PROVIDER's model and its same-provider fallback."""
    provider = settings.llm_provider
    if provider not in PROVIDERS:
        return []
    spec = PROVIDERS[provider]
    default_model, default_fallback = spec.default_models or (None, None)
    model = settings.llm_model or default_model
    if not model:
        return []
    # A custom LLM_MODEL falls back to the provider's current default, so a
    # retired or mistyped model name degrades instead of failing every call.
    fallback = settings.llm_fallback_model or (
        default_model if model != default_model else default_fallback
    )
    targets = [LLMTarget(provider, model)]
    if fallback and fallback != model:
        targets.append(LLMTarget(provider, fallback))
    return targets


def route(workflow: str, settings: Settings) -> list[LLMTarget]:
    """The ordered model chain for `workflow`: LLM_ROUTES[workflow] if set,
    else the primary chain then LLM_FALLBACKS. Models without a key are skipped."""
    if settings.llm_provider in (None, "none"):
        return []
    if workflow in settings.llm_routes:
        candidates = [LLMTarget.parse(v) for v in settings.llm_routes[workflow]]
    else:
        candidates = [
            *primary_targets(settings),
            *(LLMTarget.parse(v) for v in settings.llm_fallbacks),
        ]
    chain: list[LLMTarget] = []
    for target in candidates:
        if target and target not in chain and _usable(target, settings):
            chain.append(target)
    return chain if settings.llm_fallback_enabled else chain[:1]


_override: AIProvider | None = None


def set_ai_provider(provider: AIProvider | None) -> None:
    """Replace the configured provider (tests, scripts). Calls still go through
    the gateway, so they are rate limited and recorded like real ones."""
    global _override
    _override = provider


def ai_configured(settings: Settings | None = None) -> bool:
    if _override is not None:
        return True
    return bool(route("default", settings or get_settings()))


def get_ai_provider(
    settings: Settings | None = None, workflow: str = "default"
) -> "LLMGateway | None":
    """The gateway for `workflow`'s model chain, or None when no LLM is
    configured (callers then use rule-based logic)."""
    from app.ai.gateway import LLMGateway

    settings = settings or get_settings()
    if _override is not None:
        return LLMGateway([_override], settings)
    targets = route(workflow, settings)
    if not targets:
        return None
    return LLMGateway([build_adapter(t, settings) for t in targets], settings)
