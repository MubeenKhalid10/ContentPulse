"""Rate limiting (spec §61): login/registration brute-force protection, a
per-user cap on AI-heavy endpoints, and a per-IP cap on the whole API.

Fixed-window counters live in Redis when it's reachable, so limits hold
across API instances. Otherwise they fall back to process memory: a Redis
outage weakens the limits but never takes the API down.
"""

import math
import time
from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import logger


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window: int  # seconds
    message: str = "Too many requests. Try again in a moment."


LOGIN_PER_IP = Rule("login-ip", 30, 900, "Too many sign-in attempts. Try again in a few minutes.")
LOGIN_PER_ACCOUNT = Rule(
    "login-account", 10, 900, "Too many sign-in attempts for this account. Try again later."
)
REGISTER_PER_IP = Rule("register", 20, 3600, "Too many sign-ups from this network. Try later.")
RESET_PER_IP = Rule("reset", 10, 3600, "Too many reset requests. Try again later.")
RESET_PER_ACCOUNT = Rule(
    "reset-account", 3, 3600, "A reset link was sent recently. Check your inbox."
)
INVITE_PER_IP = Rule("invite", 30, 3600, "Too many invitation attempts. Try again later.")
AI_PER_USER = Rule(
    "ai", 30, 60, "You're generating very quickly. Wait a minute before trying again."
)


class MemoryBackend:
    name = "memory"

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, window: int) -> tuple[int, float]:
        now = time.monotonic()
        count, reset = self._counts.get(key, (0, now + window))
        if now >= reset:
            count, reset = 0, now + window
        count += 1
        self._counts[key] = (count, reset)
        if len(self._counts) > 50_000:  # drop expired windows
            self._counts = {k: v for k, v in self._counts.items() if v[1] > now}
        return count, reset - now

    def clear(self) -> None:
        self._counts.clear()


class RedisBackend:
    name = "redis"

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self.client = redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)

    async def hit(self, key: str, window: int) -> tuple[int, float]:
        async with self.client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
        return int(count), float(ttl if ttl and ttl > 0 else window)


class RateLimiter:
    PREFIX = "cp:rl:"
    RETRY_REDIS_AFTER = 60.0

    def __init__(self) -> None:
        self.memory = MemoryBackend()
        self._redis: RedisBackend | None = None
        self._redis_down_until = 0.0
        self.configure(get_settings())

    def configure(self, settings: Settings) -> None:
        self.enabled = settings.rate_limit_enabled
        self.mode = settings.rate_limit_backend
        self.redis_url = settings.redis_url
        self.per_minute = settings.api_rate_limit_per_minute
        self.trusted_proxies = settings.trusted_proxy_count
        self._redis = None

    def reset(self) -> None:
        self.memory.clear()

    async def _hit(self, key: str, window: int) -> tuple[int, float]:
        if self.mode != "memory" and time.monotonic() >= self._redis_down_until:
            try:
                if self._redis is None:
                    self._redis = RedisBackend(self.redis_url)
                return await self._redis.hit(key, window)
            except Exception as exc:
                self._redis = None
                self._redis_down_until = time.monotonic() + self.RETRY_REDIS_AFTER
                logger.warning("Rate limiting falls back to memory (Redis unavailable: %s)", exc)
        return await self.memory.hit(key, window)

    async def check(self, rule: Rule, key: str) -> None:
        """Count one request against `rule` for `key`; raise 429 when over."""
        if not self.enabled:
            return
        window_key = f"{self.PREFIX}{rule.name}:{key}"
        count, reset_in = await self._hit(window_key, rule.window)
        if count > rule.limit:
            retry_after = max(1, math.ceil(reset_in))
            raise AppError(
                ErrorCode.RATE_LIMITED,
                rule.message,
                details={"retry_after": retry_after, "limit": rule.limit, "window": rule.window},
                headers={"Retry-After": str(retry_after)},
            )

    def client_ip(self, request: Request) -> str:
        """The caller's address. X-Forwarded-For is only trusted for the hops
        our own proxies add (counted from the right), so clients can't spoof it."""
        forwarded = request.headers.get("x-forwarded-for")
        if self.trusted_proxies and forwarded:
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if hops:
                return hops[-self.trusted_proxies] if len(hops) >= self.trusted_proxies else hops[0]
        return request.client.host if request.client else "unknown"


limiter = RateLimiter()


class RateLimitMiddleware:
    """Per-IP cap on every /api request (pure ASGI: no request buffering)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and limiter.enabled
            and scope["path"].startswith("/api/")
            and scope["method"] != "OPTIONS"
        ):
            from fastapi.responses import JSONResponse

            from app.core.errors import error_body

            rule = Rule("api", limiter.per_minute, 60, "Too many requests. Slow down a little.")
            try:
                await limiter.check(rule, limiter.client_ip(Request(scope)))
            except AppError as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content=error_body(exc.code, exc.message, exc.details),
                    headers=exc.headers,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def per_user(rule: Rule):
    """Dependency: count the request against `rule` for the signed-in user."""
    from fastapi import Depends

    from app.api.deps import CurrentUser

    async def check(user: CurrentUser) -> None:
        await limiter.check(rule, str(user.id))

    return Depends(check)


def per_ip(rule: Rule):
    from fastapi import Depends

    async def check(request: Request) -> None:
        await limiter.check(rule, limiter.client_ip(request))

    return Depends(check)
