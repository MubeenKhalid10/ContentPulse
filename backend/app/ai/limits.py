"""Provider/model quotas for the LLM gateway.

Every model call reserves capacity first. RPM, TPM, requests/day, tokens/day
and concurrency are independent resources: a call proceeds only when all of
them have room (plenty of TPM never excuses an exhausted RPM). Limits come
from `llm_limits.json` (+ LLM_LIMITS overrides), scaled down by
LLM_RATE_LIMIT_SAFETY_FACTOR.

With Redis reachable, the check-and-reserve runs as one Lua script, so every
API and worker process shares the same counters. Without it, counters live in
process memory: correct for one process (TASK_BACKEND=inprocess), approximate
with several.
"""

import asyncio
import json
import math
import time
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import Settings, get_settings
from app.core.logging import logger

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREFIX = "cp:llm:"


def monotonic() -> float:
    """The gateway's clock (seconds). Tests replace it to simulate minutes."""
    return time.monotonic()


@dataclass(frozen=True)
class ModelLimits:
    """Published limits for a provider or model. None = no known limit."""

    rpm: int | None = None
    tpm: int | None = None
    rph: int | None = None  # per rolling hour (Cerebras)
    tph: int | None = None
    rpd: int | None = None
    tpd: int | None = None
    concurrency: int | None = None
    # Cap on output tokens requested from this model. Some providers (Groq)
    # count max_tokens against TPM, so a large cap can never fit.
    max_output_tokens: int | None = None
    # When daily quotas reset (Gemini: midnight Pacific).
    reset_timezone: str = "UTC"


def _parse_limits(key: str, raw: dict) -> ModelLimits | None:
    allowed = {f.name for f in fields(ModelLimits)}
    try:
        values = {k: v for k, v in raw.items() if not k.startswith("_")}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unknown fields {sorted(unknown)}")
        for name, value in values.items():
            if name != "reset_timezone" and value is not None:
                if not isinstance(value, int) or value < 0:
                    raise ValueError(f"{name} must be a whole number >= 0")
        return ModelLimits(**values)
    except (TypeError, ValueError) as exc:
        logger.error("Ignoring LLM limits for %r: %s", key, exc)
        return None


class LimitsCatalog:
    """Lookup: a model uses "provider/model", else "provider/*", else "*";
    a "provider" entry adds limits shared by all of that provider's models
    (one API key/project)."""

    def __init__(self, entries: dict[str, ModelLimits], default_concurrency: int) -> None:
        self.entries = entries
        self.default = entries.get("*") or ModelLimits(concurrency=default_concurrency)

    @classmethod
    def from_settings(cls, settings: Settings) -> "LimitsCatalog":
        raw: dict[str, dict] = {}
        name = settings.llm_limits_file
        if name and name.lower() != "off":
            path = Path(name) if Path(name).is_absolute() else BACKEND_DIR / name
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                logger.warning("LLM limits file %s not found; using defaults", path)
            except (OSError, ValueError) as exc:
                logger.error("Could not read LLM limits file %s: %s", path, exc)
        for key, override in settings.llm_limits.items():
            raw[key] = {**raw.get(key, {}), **override}
        entries = {
            key: limits
            for key, value in raw.items()
            if not key.startswith("_") and isinstance(value, dict)
            if (limits := _parse_limits(key, value)) is not None
        }
        return cls(entries, max(1, settings.llm_max_concurrency))

    def model(self, provider: str, model: str) -> ModelLimits:
        return (
            self.entries.get(f"{provider}/{model}")
            or self.entries.get(f"{provider}/*")
            or self.default
        )

    def provider(self, provider: str) -> ModelLimits | None:
        return self.entries.get(provider)


# --- Rules -------------------------------------------------------------------------

Kind = Literal["window", "counter", "lease", "cooldown"]


@dataclass
class Rule:
    """One resource a call must reserve. `window`: sliding window summing
    costs (RPM, TPM); `counter`: fixed-period total (per day); `lease`:
    concurrent calls; `cooldown`: a pause set after a provider 429."""

    key: str
    kind: Kind
    limit: int
    period_ms: int
    cost: int = 1
    # "model": the target's own quota (another model may have room);
    # "budget": the application's budget (applies to every model).
    scope: Literal["model", "budget"] = "model"
    label: str = ""
    # Cost is a token estimate, corrected to the actual count after the call.
    metered: bool = False

    @property
    def daily(self) -> bool:
        return self.kind == "counter"


def effective(limit: int | None, factor: float) -> int | None:
    if limit is None:
        return None
    return max(1, math.floor(limit * factor)) if limit > 0 else 0


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown time zone %r for LLM quotas; using UTC", name)
        return ZoneInfo("UTC")


def day_period(tz_name: str, now: datetime | None = None) -> tuple[str, int]:
    """(day stamp, ms until that day's reset) in `tz_name`."""
    tz = _zone(tz_name)
    local = (now or datetime.now(tz)).astimezone(tz)
    reset = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tz)
    return local.strftime("%Y%m%d"), max(1000, int((reset - local).total_seconds() * 1000))


def target_rules(
    scope: str, limits: ModelLimits, factor: float, tokens: int, lease_ms: int
) -> list[Rule]:
    """Rules for one provider or model scope (e.g. "gemini/gemini-3.5-flash")."""
    rules = [Rule(f"{PREFIX}cooldown:{scope}", "cooldown", 0, 0, label=f"{scope} cooldown")]
    if (rpm := effective(limits.rpm, factor)) is not None:
        rules.append(Rule(f"{PREFIX}rpm:{scope}", "window", rpm, 60_000, 1, label=f"{scope} RPM"))
    if (tpm := effective(limits.tpm, factor)) is not None:
        rules.append(
            Rule(
                f"{PREFIX}tpm:{scope}",
                "window",
                tpm,
                60_000,
                tokens,
                label=f"{scope} TPM",
                metered=True,
            )
        )
    if (rph := effective(limits.rph, factor)) is not None:
        rules.append(
            Rule(f"{PREFIX}rph:{scope}", "window", rph, 3_600_000, 1, label=f"{scope} RPH")
        )
    if (tph := effective(limits.tph, factor)) is not None:
        rules.append(
            Rule(
                f"{PREFIX}tph:{scope}",
                "window",
                tph,
                3_600_000,
                tokens,
                label=f"{scope} TPH",
                metered=True,
            )
        )
    if limits.rpd is not None or limits.tpd is not None:
        day, ttl = day_period(limits.reset_timezone)
        if (rpd := effective(limits.rpd, factor)) is not None:
            rules.append(
                Rule(f"{PREFIX}rpd:{scope}:{day}", "counter", rpd, ttl, 1, label=f"{scope} RPD")
            )
        if (tpd := effective(limits.tpd, factor)) is not None:
            rules.append(
                Rule(
                    f"{PREFIX}tpd:{scope}:{day}",
                    "counter",
                    tpd,
                    ttl,
                    tokens,
                    label=f"{scope} TPD",
                    metered=True,
                )
            )
    if limits.concurrency is not None:
        rules.append(
            Rule(
                f"{PREFIX}lease:{scope}",
                "lease",
                max(1, limits.concurrency),
                lease_ms,
                label=f"{scope} concurrency",
            )
        )
    return rules


def budget_rules(
    settings: Settings, organization_id: uuid.UUID | None, workflow: str
) -> list[Rule]:
    """Application-level daily request budgets (global, per org, per workflow)."""
    day, ttl = day_period(settings.llm_budget_timezone)
    budgets = [
        ("global", settings.llm_daily_request_budget),
        (
            f"org:{organization_id}",
            settings.llm_org_daily_request_budget if organization_id else None,
        ),
        (f"workflow:{workflow}", settings.llm_workflow_daily_budgets.get(workflow)),
    ]
    return [
        Rule(f"{PREFIX}budget:{name}:{day}", "counter", limit, ttl, 1, "budget", f"{name} budget")
        for name, limit in budgets
        if limit is not None
    ]


# --- Backends ------------------------------------------------------------------------

# KEYS: one per rule. ARGV: [n, then per rule: kind, limit, period_ms, cost, member].
# Returns {1} when every rule had room (and all were reserved), else
# {0, failing rule index (1-based), ms until it may have room}.
ACQUIRE_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local n = tonumber(ARGV[1])
local function cost_of(member) return tonumber(string.match(member, '|(%-?%d+)$')) end
for i = 1, n do
  local b = 1 + (i - 1) * 5
  local kind, limit = ARGV[b + 1], tonumber(ARGV[b + 2])
  local period, cost = tonumber(ARGV[b + 3]), tonumber(ARGV[b + 4])
  local key = KEYS[i]
  if kind == 'cooldown' then
    local ttl = redis.call('PTTL', key)
    if ttl > 0 then return {0, i, ttl} end
  elseif kind == 'window' then
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - period)
    local items = redis.call('ZRANGE', key, 0, -1, 'WITHSCORES')
    local used = 0
    for j = 1, #items, 2 do used = used + cost_of(items[j]) end
    -- An empty window admits any single call, even one larger than the limit.
    if used > 0 and used + cost > limit then
      local freed, wait = 0, period
      for j = 1, #items, 2 do
        freed = freed + cost_of(items[j])
        if used - freed + cost <= limit then wait = tonumber(items[j + 1]) + period - now break end
      end
      return {0, i, math.max(wait, 1)}
    end
  elseif kind == 'counter' then
    local used = tonumber(redis.call('GET', key) or '0')
    if used + cost > limit then return {0, i, math.max(redis.call('PTTL', key), 1)} end
  elseif kind == 'lease' then
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
    if redis.call('ZCARD', key) >= limit then return {0, i, 250} end
  end
end
for i = 1, n do
  local b = 1 + (i - 1) * 5
  local kind, member = ARGV[b + 1], ARGV[b + 5]
  local period, cost = tonumber(ARGV[b + 3]), tonumber(ARGV[b + 4])
  local key = KEYS[i]
  if kind == 'window' then
    redis.call('ZADD', key, now, member .. '|' .. cost)
    redis.call('PEXPIRE', key, period)
  elseif kind == 'counter' then
    redis.call('INCRBY', key, cost)
    if redis.call('PTTL', key) < 0 then redis.call('PEXPIRE', key, period) end
  elseif kind == 'lease' then
    redis.call('ZADD', key, now + period, member)
    redis.call('PEXPIRE', key, period)
  end
end
return {1}
"""

# Replace a window reservation's cost with the actual one (keeps its timestamp).
ADJUST_LUA = """
local member = ARGV[1] .. '|' .. ARGV[2]
local score = redis.call('ZSCORE', KEYS[1], member)
if score then
  redis.call('ZREM', KEYS[1], member)
  redis.call('ZADD', KEYS[1], score, ARGV[1] .. '|' .. ARGV[3])
end
return 1
"""


@dataclass
class Verdict:
    ok: bool
    rule: Rule | None = None
    wait: float = 0.0  # seconds


class MemoryQuotaBackend:
    name = "memory"

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.windows: dict[str, list[tuple[float, str, int]]] = {}
        self.counters: dict[str, tuple[int, float]] = {}
        self.leases: dict[str, dict[str, float]] = {}
        self.cooldowns: dict[str, float] = {}

    def clear(self) -> None:
        self.windows.clear()
        self.counters.clear()
        self.leases.clear()
        self.cooldowns.clear()

    @staticmethod
    def _now() -> float:
        return monotonic() * 1000

    async def acquire(self, rules: list[Rule], member: str) -> Verdict:
        async with self._lock:
            now = self._now()
            for rule in rules:
                if rule.kind == "cooldown":
                    until = self.cooldowns.get(rule.key, 0)
                    if until > now:
                        return Verdict(False, rule, (until - now) / 1000)
                elif rule.kind == "window":
                    items = [
                        e for e in self.windows.get(rule.key, []) if e[0] > now - rule.period_ms
                    ]
                    self.windows[rule.key] = items
                    used = sum(e[2] for e in items)
                    if used > 0 and used + rule.cost > rule.limit:
                        freed, wait = 0, rule.period_ms
                        for at, _, cost in items:
                            freed += cost
                            if used - freed + rule.cost <= rule.limit:
                                wait = at + rule.period_ms - now
                                break
                        return Verdict(False, rule, max(wait, 1) / 1000)
                elif rule.kind == "counter":
                    used, expires = self.counters.get(rule.key, (0, now + rule.period_ms))
                    if expires <= now:
                        used, expires = 0, now + rule.period_ms
                    if used + rule.cost > rule.limit:
                        return Verdict(False, rule, max(expires - now, 1) / 1000)
                elif rule.kind == "lease":
                    held = {m: e for m, e in self.leases.get(rule.key, {}).items() if e > now}
                    self.leases[rule.key] = held
                    if len(held) >= rule.limit:
                        return Verdict(False, rule, 0.25)
            for rule in rules:
                if rule.kind == "window":
                    self.windows[rule.key].append((now, member, rule.cost))
                elif rule.kind == "counter":
                    used, expires = self.counters.get(rule.key, (0, now + rule.period_ms))
                    if expires <= now:
                        used, expires = 0, now + rule.period_ms
                    self.counters[rule.key] = (used + rule.cost, expires)
                elif rule.kind == "lease":
                    self.leases[rule.key][member] = now + rule.period_ms
            return Verdict(True)

    async def release(self, key: str, member: str) -> None:
        self.leases.get(key, {}).pop(member, None)

    async def adjust(self, rule: Rule, member: str, cost: int) -> None:
        async with self._lock:
            if rule.kind == "window":
                self.windows[rule.key] = [
                    (at, m, cost if m == member else c)
                    for at, m, c in self.windows.get(rule.key, [])
                ]
            elif rule.kind == "counter" and rule.key in self.counters:
                used, expires = self.counters[rule.key]
                self.counters[rule.key] = (used + cost - rule.cost, expires)

    async def cooldown(self, key: str, seconds: float) -> None:
        self.cooldowns[key] = max(self.cooldowns.get(key, 0), self._now() + seconds * 1000)


class RedisQuotaBackend:
    name = "redis"

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        # Generous read timeout: a busy Redis is slow, not down.
        self.client = redis.from_url(url, socket_timeout=3.0, socket_connect_timeout=1.0)
        self._acquire = self.client.register_script(ACQUIRE_LUA)
        self._adjust = self.client.register_script(ADJUST_LUA)

    async def acquire(self, rules: list[Rule], member: str) -> Verdict:
        args: list = [len(rules)]
        for rule in rules:
            args += [rule.kind, rule.limit, rule.period_ms, rule.cost, member]
        result = await self._acquire(keys=[r.key for r in rules], args=args)
        if int(result[0]) == 1:
            return Verdict(True)
        return Verdict(False, rules[int(result[1]) - 1], int(result[2]) / 1000)

    async def release(self, key: str, member: str) -> None:
        await self.client.zrem(key, member)

    async def adjust(self, rule: Rule, member: str, cost: int) -> None:
        if rule.kind == "window":
            await self._adjust(keys=[rule.key], args=[member, rule.cost, cost])
        elif rule.kind == "counter":
            await self.client.incrby(rule.key, cost - rule.cost)

    async def cooldown(self, key: str, seconds: float) -> None:
        ms = max(1, int(seconds * 1000))
        # Never shorten a longer cooldown another process already set.
        current = await self.client.pttl(key)
        if current < ms:
            await self.client.set(key, "1", px=ms)


@dataclass
class Reservation:
    """Capacity held by one call. Release it when the call ends."""

    limiter: "QuotaLimiter"
    backend: MemoryQuotaBackend | RedisQuotaBackend
    member: str
    rules: list[Rule]
    waited: float
    released: bool = field(default=False)

    async def release(self, actual_tokens: int | None = None) -> None:
        """Free the concurrency slot; replace the token estimate with the actual
        count when the provider reported one."""
        if self.released:
            return
        self.released = True
        try:
            for rule in self.rules:
                if rule.kind == "lease":
                    await self.backend.release(rule.key, self.member)
                elif rule.metered and actual_tokens is not None:
                    await self.backend.adjust(rule, self.member, actual_tokens)
        except Exception as exc:  # leases expire on their own
            logger.warning("Could not release LLM reservation: %s", exc)


class QuotaExceeded(Exception):
    """No capacity before the deadline. `rule.daily`: it won't clear today."""

    def __init__(self, rule: Rule, wait: float) -> None:
        super().__init__(f"{rule.label} reached")
        self.rule = rule
        self.wait = wait


class QuotaLimiter:
    RETRY_REDIS_AFTER = 60.0
    MAX_POLL = 5.0

    def __init__(self) -> None:
        self.memory = MemoryQuotaBackend()
        self._redis: RedisQuotaBackend | None = None
        self._redis_down_until = 0.0
        self._catalog: LimitsCatalog | None = None
        self.sleep = asyncio.sleep
        self.configure(get_settings())

    def configure(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.llm_limiter_backend
        self._redis = None
        self._redis_down_until = 0.0
        self._catalog = None

    @property
    def catalog(self) -> LimitsCatalog:
        if self._catalog is None:
            self._catalog = LimitsCatalog.from_settings(self.settings)
        return self._catalog

    def reset(self) -> None:
        self.memory.clear()

    def backend(self) -> MemoryQuotaBackend | RedisQuotaBackend:
        if self.mode != "memory" and monotonic() >= self._redis_down_until:
            if self._redis is None:
                self._redis = RedisQuotaBackend(self.settings.redis_url)
            return self._redis
        return self.memory

    def _redis_failed(self, exc: Exception) -> None:
        if self.mode == "redis":
            # Strict mode: never fall back to unshared counters. Report it as
            # a transient outage so the job is retried, not crashed.
            from app.ai.provider import AIError, AIErrorKind

            raise AIError(
                AIErrorKind.UNAVAILABLE, f"LLM rate limiter unavailable (Redis: {exc})."
            ) from exc
        self._redis = None
        self._redis_down_until = monotonic() + self.RETRY_REDIS_AFTER
        logger.warning("LLM quotas fall back to process memory (Redis unavailable: %s)", exc)

    def rules(
        self,
        provider: str,
        model: str,
        *,
        tokens: int,
        organization_id: uuid.UUID | None,
        workflow: str,
    ) -> list[Rule]:
        factor = min(1.0, max(0.05, self.settings.llm_rate_limit_safety_factor))
        # A lease outlives a crashed caller by a margin, then frees itself.
        lease_ms = int((self.settings.llm_timeout_seconds + 60) * 1000)
        rules = budget_rules(self.settings, organization_id, workflow)
        provider_limits = self.catalog.provider(provider)
        if provider_limits is not None:
            rules += target_rules(provider, provider_limits, factor, tokens, lease_ms)
        rules += target_rules(
            f"{provider}/{model}", self.catalog.model(provider, model), factor, tokens, lease_ms
        )
        return rules

    async def acquire(
        self,
        provider: str,
        model: str,
        *,
        tokens: int,
        organization_id: uuid.UUID | None,
        workflow: str,
        deadline: float,
    ) -> Reservation:
        """Wait (up to `deadline`, monotonic seconds) until every rule has room,
        then reserve them all at once. Raises QuotaExceeded."""
        rules = self.rules(
            provider, model, tokens=tokens, organization_id=organization_id, workflow=workflow
        )
        member = uuid.uuid4().hex
        started = monotonic()
        redis_retried = False
        while True:
            backend = self.backend()
            try:
                verdict = await backend.acquire(rules, member)
            except Exception as exc:
                if backend is self.memory:
                    raise
                if not redis_retried:
                    # A busy Redis can miss one read: try once more first.
                    redis_retried = True
                    await self.sleep(0.2)
                    continue
                self._redis_failed(exc)
                continue
            if verdict.ok:
                return Reservation(self, backend, member, rules, monotonic() - started)
            assert verdict.rule is not None
            if verdict.rule.daily or monotonic() + verdict.wait > deadline:
                raise QuotaExceeded(verdict.rule, verdict.wait)
            # Poll: a finished call can free a slot before the window says so.
            await self.sleep(min(verdict.wait, self.MAX_POLL) + 0.05)

    async def cooldown(self, provider: str, model: str, seconds: float) -> None:
        """Pause a model for every process (after the provider said 429)."""
        if seconds <= 0:
            return
        key = f"{PREFIX}cooldown:{provider}/{model}"
        backend = self.backend()
        try:
            await backend.cooldown(key, seconds)
        except Exception as exc:
            if backend is self.memory:
                raise
            self._redis_failed(exc)
            await self.memory.cooldown(key, seconds)


quota_limiter = QuotaLimiter()


def estimate_tokens(*texts: str) -> int:
    """Rough input size (≈4 characters per token) used only to reserve TPM;
    the provider's reported usage replaces it after the call."""
    return max(1, sum(len(t) for t in texts) // 4)
