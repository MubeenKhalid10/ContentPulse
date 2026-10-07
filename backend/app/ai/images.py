"""AI image generation for design tasks.

Adapters make one request each; `generate_image` runs it through the LLM
gateway's quotas (llm_limits.json), retries and accounting (llm_requests,
workflow "design_image"). Providers:
  kie        -> Kie AI market models (Seedream, ...): create task, poll, download
  cloudflare -> Cloudflare Workers AI (Leonardo, FLUX, Stable Diffusion models)
  gemini     -> Gemini image models (generateContent with IMAGE output)
  openai     -> OpenAI Images API (gpt-image-1)
IMAGE_PROVIDER empty = the first provider set up (Kie, Cloudflare, Gemini, OpenAI),
else off. "none" turns it off.
"""

import asyncio
import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.ai import limits
from app.ai.provider import (
    AIError,
    AIErrorKind,
    GeminiProvider,
    OpenAICompatibleProvider,
    api_key_for,
    retry_after_from,
)
from app.core.config import Settings, get_settings
from app.core.logging import logger

DEFAULT_MODELS = {
    # Kie AI's cheapest text-to-image model (credits per image).
    "kie": "seedream/5-flash-text-to-image",
    # ~173 neurons per image (about 57 a day on the free plan); square output.
    # @cf/leonardo/lucid-origin draws text better and takes sizes, but costs
    # ~2,800 neurons (about 3 a day on the free plan).
    "cloudflare": "@cf/black-forest-labs/flux-1-schnell",
    "gemini": "gemini-2.5-flash-image",
    "openai": "gpt-image-1",
}
# Aspect ratios image models accept, as width / height.
RATIOS = {
    "1:1": 1.0,
    "4:5": 0.8,
    "5:4": 1.25,
    "3:4": 0.75,
    "4:3": 4 / 3,
    "2:3": 2 / 3,
    "3:2": 1.5,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "21:9": 21 / 9,
}
NOT_IN_PLAN = (
    "AI image generation isn't included in your AI provider plan (its free tier allows 0 "
    "images). Enable billing for the API key, or set IMAGE_PROVIDER to another provider."
)


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str
    provider: str
    model: str


def aspect_ratio(dimensions: str | None) -> str:
    """The supported ratio closest to a brief's dimensions ("1080×1350 (4:5)")."""
    match = re.search(r"(\d{2,5})\s*[×xX*]\s*(\d{2,5})", dimensions or "")
    if not match:
        return "1:1"
    wanted = int(match.group(1)) / int(match.group(2))
    return min(RATIOS, key=lambda r: abs(RATIOS[r] - wanted))


def _plan_error(message: str) -> AIError | None:
    """Google says "limit: 0" when a model isn't available on the key's plan."""
    if "limit: 0" in message:
        return AIError(AIErrorKind.QUOTA_EXHAUSTED, NOT_IN_PLAN, public=True)
    return None


class GeminiImages:
    name = "gemini"
    BASE_URL = GeminiProvider.BASE_URL

    def __init__(self, *, model: str, api_key: str, timeout: float, client=None) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = client

    async def generate(self, prompt: str, ratio: str) -> GeneratedImage:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": ratio},
            },
        }
        url = f"{self.BASE_URL}/models/{self.model}:generateContent"
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(url, json=body, headers={"x-goog-api-key": self._api_key})
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach Gemini ({type(exc).__name__})."
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code != 200:
            raise _plan_error(resp.text) or GeminiProvider._error(resp)
        data = resp.json()
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise AIError(AIErrorKind.REFUSED, f"Gemini blocked the image request ({block}).")
        for candidate in data.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return GeneratedImage(
                        data=base64.b64decode(inline["data"]),
                        mime_type=inline.get("mimeType") or inline.get("mime_type") or "image/png",
                        provider=self.name,
                        model=data.get("modelVersion") or self.model,
                    )
        finish = ((data.get("candidates") or [{}])[0]).get("finishReason")
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "IMAGE_SAFETY", "BLOCKLIST"):
            raise AIError(AIErrorKind.REFUSED, f"Gemini declined to draw this ({finish}).")
        raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no image.")


class OpenAIImages:
    name = "openai"
    SIZES = {"square": "1024x1024", "wide": "1536x1024", "tall": "1024x1536"}

    def __init__(
        self, *, model: str, api_key: str, base_url: str, timeout: float, client=None
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/images/generations"
        self._timeout = timeout
        self._client = client
        # Same error mapping as OpenAI chat calls.
        self._errors = OpenAICompatibleProvider(
            name="openai", model=model, api_key="", base_url=base_url, timeout=timeout
        )

    async def generate(self, prompt: str, ratio: str) -> GeneratedImage:
        shape = RATIOS[ratio]
        size = self.SIZES["wide" if shape > 1.15 else "tall" if shape < 0.87 else "square"]
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(
                self._url,
                json={"model": self.model, "prompt": prompt, "size": size, "n": 1},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach OpenAI ({type(exc).__name__})."
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code != 200:
            raise self._errors._error(resp)
        items = resp.json().get("data") or []
        if not items or not items[0].get("b64_json"):
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no image.")
        return GeneratedImage(
            data=base64.b64decode(items[0]["b64_json"]),
            mime_type="image/png",
            provider=self.name,
            model=self.model,
        )


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


class CloudflareImages:
    """Cloudflare Workers AI text-to-image (`/ai/run/{model}`)."""

    name = "cloudflare"
    # FLUX.1 [schnell] has a fixed size; the others take width and height.
    FIXED_SIZE = ("flux-1-schnell",)
    MAX_PROMPT = 2000

    def __init__(
        self, *, model: str, account_id: str, api_token: str, timeout: float, client=None
    ) -> None:
        self.model = model
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        self._token = api_token
        self._timeout = timeout
        self._client = client

    @staticmethod
    def size(ratio: str, long_side: int = 1280) -> tuple[int, int]:
        """Width and height for a ratio, multiples of 16, long side ~1280px."""
        shape = RATIOS[ratio]
        width, height = (
            (long_side, long_side / shape) if shape >= 1 else (long_side * shape, long_side)
        )
        return int(width) // 16 * 16, int(height) // 16 * 16

    def _error(self, resp: httpx.Response) -> AIError:
        try:
            body = resp.json()
            detail = (
                "; ".join(str(e.get("message", e)) for e in body.get("errors") or [])
                or resp.text[:200]
            )
        except ValueError:
            detail = resp.text[:200]
        lowered = detail.lower()
        if resp.status_code in (401, 403):
            return AIError(AIErrorKind.AUTH, f"Cloudflare rejected the API token: {detail[:150]}")
        if resp.status_code == 429:
            if "daily" in lowered or "neuron" in lowered or "allocation" in lowered:
                return AIError(
                    AIErrorKind.QUOTA_EXHAUSTED,
                    "Today's free Cloudflare AI allowance is used up. Try again tomorrow, or "
                    "upgrade the Cloudflare plan.",
                    public=True,
                )
            return AIError(
                AIErrorKind.RATE_LIMITED,
                "Cloudflare rate limit reached.",
                retry_after=retry_after_from(resp.headers),
            )
        if resp.status_code >= 500:
            return AIError(AIErrorKind.UNAVAILABLE, f"Cloudflare error ({resp.status_code}).")
        if resp.status_code == 404 or "no such model" in lowered:
            return AIError(
                AIErrorKind.MODEL_UNAVAILABLE, f"Cloudflare model unavailable: {detail[:150]}"
            )
        return AIError(AIErrorKind.BAD_REQUEST, f"Cloudflare rejected the request: {detail[:200]}")

    async def generate(self, prompt: str, ratio: str) -> GeneratedImage:
        body: dict = {"prompt": prompt[: self.MAX_PROMPT]}
        if not any(m in self.model for m in self.FIXED_SIZE):
            body["width"], body["height"] = self.size(ratio)
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach Cloudflare ({type(exc).__name__})."
            ) from exc
        finally:
            if self._client is None:
                await client.aclose()
        if resp.status_code != 200:
            raise self._error(resp)
        content_type = resp.headers.get("content-type", "")
        if content_type.startswith("image/"):  # e.g. Stable Diffusion returns raw PNG
            data = resp.content
        else:
            result = (resp.json() or {}).get("result") or {}
            encoded = result.get("image") if isinstance(result, dict) else None
            if not encoded:
                raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no image.")
            data = base64.b64decode(encoded)
        if not data:
            raise AIError(AIErrorKind.BAD_OUTPUT, "The AI returned no image.")
        return GeneratedImage(
            data=data, mime_type=_mime(data), provider=self.name, model=self.model
        )


class KieImages:
    """Kie AI market models: create a task, poll it, then download the image
    (result links expire after 24 hours, so the file is stored right away)."""

    name = "kie"
    BASE_URL = "https://api.kie.ai/api/v1/jobs"
    # Ratios Seedream accepts; others map to the nearest of these.
    RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9")
    POLL_SECONDS = 3.0
    MAX_PROMPT = 5000

    def __init__(self, *, model: str, api_key: str, timeout: float, client=None) -> None:
        self.model = model
        self._key = api_key
        self._timeout = timeout
        self._client = client
        self.sleep = asyncio.sleep

    def _ratio(self, ratio: str) -> str:
        if ratio in self.RATIOS:
            return ratio
        return min(self.RATIOS, key=lambda r: abs(RATIOS[r] - RATIOS[ratio]))

    @staticmethod
    def _error(code: int, message: str, retry_after: float | None = None) -> AIError:
        if code == 401:
            return AIError(AIErrorKind.AUTH, f"Kie AI rejected the API key: {message[:150]}")
        if code == 402:
            return AIError(
                AIErrorKind.QUOTA_EXHAUSTED,
                "Your Kie AI credits have run out. Top up the account to generate more images.",
                public=True,
            )
        if code == 429:
            return AIError(
                AIErrorKind.RATE_LIMITED, "Kie AI rate limit reached.", retry_after=retry_after
            )
        if code >= 500:
            return AIError(AIErrorKind.UNAVAILABLE, f"Kie AI error ({code}): {message[:150]}")
        return AIError(
            AIErrorKind.BAD_REQUEST, f"Kie AI rejected the request ({code}): {message[:200]}"
        )

    async def _call(self, client: httpx.AsyncClient, method: str, url: str, **kwargs) -> dict:
        try:
            resp = await client.request(
                method, url, headers={"Authorization": f"Bearer {self._key}"}, **kwargs
            )
        except httpx.HTTPError as exc:
            raise AIError(
                AIErrorKind.UNAVAILABLE, f"Could not reach Kie AI ({type(exc).__name__})."
            ) from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        # Errors come back as HTTP errors or as {"code": 4xx} in a 200 body.
        code = (
            int(body.get("code") or resp.status_code)
            if isinstance(body, dict)
            else resp.status_code
        )
        if resp.status_code != 200 or code != 200:
            raise self._error(
                code if code != 200 else resp.status_code,
                str(body.get("msg") if isinstance(body, dict) else resp.text),
                retry_after_from(resp.headers),
            )
        return body.get("data") or {}

    async def generate(self, prompt: str, ratio: str) -> GeneratedImage:
        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            task = await self._call(
                client,
                "POST",
                f"{self.BASE_URL}/createTask",
                json={
                    "model": self.model,
                    "input": {
                        "prompt": prompt[: self.MAX_PROMPT],
                        "aspect_ratio": self._ratio(ratio),
                        "output_format": "png",
                    },
                },
            )
            task_id = task.get("taskId")
            if not task_id:
                raise AIError(AIErrorKind.BAD_OUTPUT, "Kie AI didn't return a task id.")
            waited = 0.0
            while True:
                await self.sleep(self.POLL_SECONDS)
                waited += self.POLL_SECONDS
                info = await self._call(
                    client, "GET", f"{self.BASE_URL}/recordInfo", params={"taskId": task_id}
                )
                state = info.get("state")
                if state == "success":
                    break
                if state == "fail":
                    reason = str(info.get("failMsg") or info.get("failCode") or "unknown reason")
                    kind = (
                        AIErrorKind.REFUSED
                        if re.search(r"sensitive|nsfw|safety|policy", reason, re.I)
                        else AIErrorKind.BAD_OUTPUT
                    )
                    raise AIError(kind, f"Kie AI couldn't create the image: {reason[:200]}")
                if waited >= self._timeout:
                    # Not retried: a second task would be charged again.
                    raise AIError(
                        AIErrorKind.BAD_OUTPUT, "Kie AI took too long to create the image."
                    )
            try:
                urls = json.loads(info.get("resultJson") or "{}").get("resultUrls") or []
            except ValueError:
                urls = []
            if not urls:
                raise AIError(AIErrorKind.BAD_OUTPUT, "Kie AI returned no image.")
            try:
                download = await client.get(urls[0], timeout=60, follow_redirects=True)
            except httpx.HTTPError as exc:
                raise AIError(
                    AIErrorKind.BAD_OUTPUT, "Couldn't download the image from Kie AI."
                ) from exc
            if download.status_code != 200 or not download.content:
                raise AIError(AIErrorKind.BAD_OUTPUT, "Couldn't download the image from Kie AI.")
            data = download.content
            return GeneratedImage(
                data=data, mime_type=_mime(data), provider=self.name, model=self.model
            )
        finally:
            if self._client is None:
                await client.aclose()


def cloudflare_credentials(settings: Settings) -> tuple[str, str] | None:
    token = settings.cloudflare_api_token or settings.cloudflare_api_key
    if settings.cloudflare_account_id and token:
        return settings.cloudflare_account_id, token
    return None


_override = None


def set_image_provider(provider) -> None:
    """Replace the configured image provider (tests)."""
    global _override
    _override = provider


def get_image_provider(settings: Settings | None = None):
    """The configured image adapter, or None when AI images are off."""
    if _override is not None:
        return _override
    settings = settings or get_settings()
    choice = settings.image_provider
    if choice == "none":
        return None
    cloudflare = cloudflare_credentials(settings)
    if choice is None:  # auto: the first provider that's set up
        if settings.kie_ai_api_key:
            choice = "kie"
        elif cloudflare:
            choice = "cloudflare"
        else:
            choice = next((p for p in ("gemini", "openai") if api_key_for(p, settings)), None)
    if choice is None:
        return None
    model = settings.image_model or DEFAULT_MODELS[choice]
    timeout = settings.llm_timeout_seconds
    if choice == "kie":
        if not settings.kie_ai_api_key:
            return None
        return KieImages(model=model, api_key=settings.kie_ai_api_key, timeout=timeout)
    if choice == "cloudflare":
        if not cloudflare:
            return None
        account_id, token = cloudflare
        return CloudflareImages(
            model=model, account_id=account_id, api_token=token, timeout=timeout
        )
    key = api_key_for(choice, settings)
    if not key:
        return None
    if choice == "gemini":
        return GeminiImages(model=model, api_key=key, timeout=timeout)
    base_url = settings.llm_base_urls.get("openai") or "https://api.openai.com/v1"
    return OpenAIImages(model=model, api_key=key, base_url=base_url, timeout=timeout)


async def generate_image(
    prompt: str,
    ratio: str,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> GeneratedImage:
    """One image through the gateway's quotas, retries and accounting."""
    from app.ai.gateway import backoff, record
    from app.ai.limits import QuotaExceeded, estimate_tokens, quota_limiter
    from app.ai.metrics import metrics

    settings = settings or get_settings()
    adapter = get_image_provider(settings)
    if adapter is None:
        raise AIError(AIErrorKind.NOT_CONFIGURED, "AI images aren't set up.", public=True)
    workflow = "design_image"
    labels = {"provider": adapter.name, "model": adapter.model, "workflow": workflow}
    call_id = uuid.uuid4()
    deadline = limits.monotonic() + settings.llm_queue_timeout_background
    retries = 0
    while True:
        try:
            reservation = await quota_limiter.acquire(
                adapter.name,
                adapter.model,
                tokens=estimate_tokens(prompt),
                organization_id=organization_id,
                workflow=workflow,
                deadline=deadline,
            )
        except QuotaExceeded as exc:
            metrics.inc("llm_rate_limit_total", source="local", **labels)
            if exc.rule.scope == "budget":
                raise AIError(
                    AIErrorKind.BUDGET_EXHAUSTED, f"AI budget reached: {exc.rule.label}."
                ) from exc
            kind = AIErrorKind.QUOTA_EXHAUSTED if exc.rule.daily else AIErrorKind.RATE_LIMITED
            raise AIError(
                kind, f"Local limit reached: {exc.rule.label}.", retry_after=exc.wait
            ) from exc
        metrics.inc("llm_requests_total", **labels)
        started_at, started = datetime.now(UTC), limits.monotonic()
        row = {
            "call_id": call_id,
            "job_id": job_id,
            "organization_id": organization_id,
            "workflow": workflow,
            "provider": adapter.name,
            "model": adapter.model,
            "attempt": retries + 1,
            "retry_count": retries,
            "fallback_used": False,
            "queue_wait_ms": int(reservation.waited * 1000),
            "started_at": started_at,
        }
        try:
            image = await adapter.generate(prompt, ratio)
        except AIError as exc:
            await reservation.release()
            metrics.inc("llm_requests_failed_total", error=exc.kind.value, **labels)
            await record(
                **row,
                status="failed",
                error_kind=exc.kind.value,
                error_detail=exc.message,
                latency_ms=int((limits.monotonic() - started) * 1000),
                completed_at=datetime.now(UTC),
                usage_unavailable=True,
            )
            if exc.retryable and retries < settings.llm_max_retries:
                delay = (
                    exc.retry_after if exc.retry_after is not None else backoff(retries, settings)
                )
                await quota_limiter.cooldown(adapter.name, adapter.model, delay)
                if delay <= settings.llm_retry_max_delay and limits.monotonic() + delay < deadline:
                    retries += 1
                    metrics.inc("llm_retries_total", **labels)
                    logger.warning(
                        "Image generation %s; retry %d in %.1fs", exc.kind.value, retries, delay
                    )
                    await quota_limiter.sleep(delay)
                    continue
            raise
        except BaseException:
            await reservation.release()
            raise
        await reservation.release()
        metrics.inc("llm_requests_success_total", **labels)
        await record(
            **row,
            status="succeeded",
            latency_ms=int((limits.monotonic() - started) * 1000),
            completed_at=datetime.now(UTC),
            usage_unavailable=True,
        )
        return image
