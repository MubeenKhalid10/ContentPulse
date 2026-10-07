# LLM gateway

Every model request ContentPulse makes goes through one layer:
`backend/app/ai/gateway.py` (`LLMGateway`) for generative calls and
`backend/app/ai/embeddings.py` (`GatedEmbeddings`) for embeddings. The gateway
decides **whether a request may be sent now**, sends it, retries or falls back
when that makes sense, and records what happened. Workflows don't know any of
this: they call `get_ai_provider(workflow=...)` and `generate_structured(...)`
as before.

```
 trend analysis   strategy draft   post generation   design brief   KB indexing / search
        \               |                 |               /                 |
         +--------------+--------+--------+--------------+          GatedEmbeddings
                                 v                                          |
                           LLMGateway  <------------------------------------+
                                 |
        cache (opt-in, per organization) -> hit: answer, no request
                                 |
        for each model in the workflow's chain (primary first):
            quota_limiter.acquire   RPM, TPM, RPD, TPD, concurrency, cooldown,
                                    app budgets: all must have room; else wait
                                    in line (up to the queue timeout)
            adapter.generate_structured   one provider request
            transient failure -> backoff / Retry-After, retry the same model
            failure another model can fix -> next model
                                 |
        llm_requests row + metrics for every request
                                 |
       GeminiProvider   AnthropicProvider   OpenAICompatibleProvider (OpenAI, Groq,
                                            Cerebras, OpenRouter)
```

Adapters (`backend/app/ai/provider.py`) make exactly one HTTP request each and
translate their vendor's errors into shared kinds. They contain no retry loops,
and the Anthropic SDK runs with `max_retries=0`, so no request goes out unseen.

## 1. Audit (before this change)

### Where models were called

| File | Function | Provider / model | Purpose | Concurrent? | Background? |
|---|---|---|---|---|---|
| `services/alignment/engines.py` | `align_with_ai` (from `service.run_job`) | `LLM_PROVIDER` / `LLM_MODEL`, then `LLM_FALLBACK_MODEL` | trend alignment | yes: `analyze_organization` runs up to 15 jobs with `asyncio.gather` + a per-process `Semaphore(3)`; manual "Analyze" adds more | yes (`trends.align_organization`, `trends.align`) |
| `services/content/generation.py` | `_generate_with_ai` | same | post copy (generate, regenerate, variant) | yes, one job per post | yes (`content.generate`) |
| `services/design/briefs.py` | `run_ai_brief` | same | design brief | yes | yes (`design.brief`) |
| `services/topics/strategies.py` | `suggest_strategy` | same | strategy draft | per request | **no**: inside the API request |
| `services/knowledge/indexer.py` | `index_document` → `embed` | `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | chunk embeddings, batches of 64 | crawl concurrency | yes (`knowledge.crawl`, `knowledge.reindex`) |
| `services/knowledge/search.py` | `search_knowledge` → `embed` | same | query embedding | from KB search, every trend analysis and every post generation | both |

No streaming, no free-text generation, and no OpenAI/Groq/Cerebras/OpenRouter
chat calls existed.

### Requests per workflow (happy path)

| Workflow | Model requests |
|---|---|
| Trend discovery run | 0 (sources, deterministic clustering and scoring), then it triggers alignment |
| Alignment after discovery | 1 per trend × up to `ALIGNMENT_AI_BATCH_SIZE` (15) = **15 per run per organization** (+1 query embedding each when embeddings are on) |
| Manual "Analyze" | 1 (+1 embedding) |
| Strategy draft | 1 |
| Post generate / regenerate / variant | 1 (+1 embedding) |
| Design brief | 1 per send-to-design |
| Knowledge crawl | ceil(chunks / 64) embedding requests per page |

### What caused the 16/15 RPM

One user action did **not** mean one request:

- `GeminiProvider` made up to 3 attempts per model (2s and 4s apart) and then up
  to 3 more on the fallback model: **up to 6 requests per logical call**. The
  Anthropic SDK did the same with `max_retries=2` plus the fallback model.
- On top of that, the job was re-queued twice (30s, 120s): **up to 18 requests
  for one trend analysis**.
- After a discovery run, 15 trends were analyzed 3 at a time. With 2–6s
  latency that is 15 requests in well under a minute, which is exactly the
  limit. The first 429 then added retries 2–4s later, inside the same minute.
- The only limiter was an `asyncio.Semaphore` **per process**: each Celery
  worker, the API, and every organization's discovery run had its own, all on
  the same API key. RPD and TPM were not tracked at all.

### Consolidation and deterministic logic

- **No consolidation was needed.** Every workflow already sends one structured
  request per unit of work. The alignment schema returns classification, fit,
  audience relevance, matched services, angles and evidence together. There are
  no chains of small sequential calls to merge.
- **Considered and rejected for now: batching several trends into one
  alignment request.** It would cut RPM by roughly the batch size, but:
  - each trend has its own knowledge passages, so prompts grow quickly;
  - one malformed item would fail the whole batch;
  - per-trend reasoning quality is harder to keep.
  
  Pacing fixes the incident without that trade-off. Revisit if RPD (not RPM)
  becomes the binding limit.
- **Deterministic work already runs without a model:**
  - normalization, clustering and deduplication;
  - freshness, velocity and opportunity scoring;
  - keyword matching and platform recommendation;
  - grounding corrections, and hashtag, length and forbidden-term checks;
  - the rule-based fallback engines.
  
  No model call was replaced.
- **New:** an identical trend analysis is answered from the cache (section 6)
  instead of a new request.

## 2. Configuring limits

Limits live in `backend/llm_limits.json`. Every field is optional:

```json
{
  "gemini/gemini-3.1-flash-lite": { "rpm": 15, "tpm": 250000, "rpd": 500, "concurrency": 2,
                                    "reset_timezone": "America/Los_Angeles" },
  "gemini/*":   { "rpm": 10, "tpm": 250000, "rpd": 250, "concurrency": 2,
                  "reset_timezone": "America/Los_Angeles" },
  "gemini":     { "concurrency": 3 },
  "groq/*":     { "rpm": 30, "concurrency": 3 },
  "*":          { "concurrency": 3 }
}
```

- **How a model finds its limits:** it uses `provider/model`, else
  `provider/*`, else `*`.
- **Provider-wide limits:** a bare `provider` entry adds limits shared by all
  of that provider's models (one key or project).
- **Fields:**
  - `rpm` and `tpm`: requests and tokens per rolling minute;
  - `rph` and `tph`: per rolling hour (Cerebras has hourly limits);
  - `rpd` and `tpd`: per day, reset at midnight in `reset_timezone`;
  - `concurrency`: requests in flight at once;
  - `max_output_tokens`: cap on the output requested from that model. Groq
    counts `max_tokens` against its 8K TPM, so an uncapped request could never
    fit.
- **Shipped numbers:** the Groq and Cerebras entries were read from their
  `x-ratelimit-*` response headers (free tier, 2026-10-06). The rest are entry
  and free-tier figures. Set them to your account's tier.
- **Overrides without editing the file:** use
  `LLM_LIMITS='{"gemini/*": {"rpm": 1000, "rpd": 10000}}'`. Fields merge into
  the file's entry.
- **No limits at all:** `LLM_LIMITS_FILE=off`.
- **Unknown or invalid entries** are logged and ignored. A model with no
  matching entry gets `concurrency = LLM_MAX_CONCURRENCY` and nothing else.

**To change a limit:** edit the file, or set `LLM_LIMITS`, then restart the
API and workers.

**To add a model:** add a `provider/model` entry, or rely on `provider/*`.

### All settings

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | unset | `gemini`, `anthropic`, `openai`, `groq`, `cerebras`, `openrouter`, or `none`. Unset or `none` uses the rule-based engines. |
| `LLM_API_KEY` | | Key for `LLM_PROVIDER`. |
| `LLM_MODEL`, `LLM_FALLBACK_MODEL` | provider default | The primary model and a same-provider fallback. Defaults: gemini `gemini-3.8-flash` → `gemini-3.5-flash`; anthropic `claude-opus-5-5` → `claude-opus-5`; groq `openai/gpt-oss-120b` → `qwen/qwen3.8-27b`; cerebras `gpt-oss-120b` → `qwen-3.8-27b`. OpenAI and OpenRouter need `LLM_MODEL`. |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` | | Keys for fallback providers. A model without a key is skipped. |
| `LLM_BASE_URLS` | `{}` | Endpoint override per OpenAI-compatible provider, e.g. `{"openai": "https://proxy/v1"}`. |
| `LLM_FALLBACKS` | empty | Models tried in order after the primary chain, comma-separated (or a JSON list): `gemini/gemini-3.1-flash-lite, groq/openai/gpt-oss-120b, cerebras/qwen-3.8-27b`. |
| `LLM_ROUTES` | `{}` | A chain per workflow (first entry = primary): `{"trend_alignment": ["gemini/gemini-3.5-flash", "groq/..."]}`. |
| `LLM_FALLBACK_ENABLED` | `true` | `false` uses only the first model. |
| `LLM_LIMITS_FILE`, `LLM_LIMITS` | `llm_limits.json`, `{}` | See above. |
| `LLM_RATE_LIMIT_SAFETY_FACTOR` | `0.8` | Run at this share of published `rpm`, `tpm`, `rpd` and `tpd`. |
| `LLM_MAX_CONCURRENCY` | `3` | Concurrency for models without a configured value. |
| `LLM_LIMITER_BACKEND` | `auto` | `auto` uses Redis when reachable, otherwise process memory. Also `redis` or `memory`. |
| `LLM_MAX_RETRIES` | `2` | Retries per model for transient errors. |
| `LLM_RETRY_BASE_DELAY`, `LLM_RETRY_MAX_DELAY` | `2`, `60` s | Backoff bounds. A `Retry-After` longer than the max moves on instead of waiting. |
| `LLM_QUEUE_TIMEOUT_INTERACTIVE` | `20` s | Longest wait for capacity when someone is waiting on the response (strategy drafts, KB search). |
| `LLM_QUEUE_TIMEOUT_BACKGROUND` | `600` s | Longest wait for background jobs. |
| `LLM_CACHE_TTL_SECONDS` | `86400` | `0` turns the cache off. |
| `LLM_DAILY_REQUEST_BUDGET` | unset | Application-wide requests per day. |
| `LLM_ORG_DAILY_REQUEST_BUDGET` | unset | Requests per organization per day. |
| `LLM_WORKFLOW_DAILY_BUDGETS` | `{}` | Per workflow, e.g. `{"trend_alignment": 300}`. |
| `LLM_BUDGET_TIMEZONE` | `UTC` | When budgets reset. |
| `METRICS_ENABLED` | `false` | Serve Prometheus metrics at `/health/metrics`. |

Workflow names: `trend_alignment`, `content_strategy`, `post_generation`,
`design_brief`, `knowledge_embedding`, `knowledge_search`.

## 3. How rate limiting works

Before each request, the gateway builds a list of independent resources and
**reserves all of them at once, or none**:

| Resource | Kind | Cost |
|---|---|---|
| RPM | rolling 60s window | 1 |
| TPM | rolling 60s window | estimated input tokens (characters ÷ 4), corrected to the provider's reported total after the call |
| RPD / TPD | counter until the daily reset | 1 / tokens |
| Concurrency | leases released when the call ends (or expire after timeout + 60s if a worker dies) | 1 |
| Cooldown | a pause set when a provider answers 429 or 503 | none |
| Budgets (global, organization, workflow) | daily counter | 1 |

**The resources are independent of each other:**

- Plenty of TPM never excuses an exhausted RPM.
- A large TPM total doesn't block a request when RPM has room and the tokens
  fit.
- An empty TPM window always admits a single request, even one larger than
  the limit, so it can't deadlock.

**Safety margin:** effective limit = floor(limit × `LLM_RATE_LIMIT_SAFETY_FACTOR`).
A 15 RPM model runs at 12.

**Shared across processes:** with Redis reachable, the check and the
reservation run as one Lua script on Redis's clock. The API and every Celery
worker draw from the same counters, so 5 workers can never send 5× the limit.

- **Without Redis:** counters live in process memory. That is exact for the
  default single-process setup (`TASK_BACKEND=inprocess`) and approximate with
  several processes.
- **If Redis drops mid-run:** the limiter falls back to memory and retries
  Redis after 60s. Set `LLM_LIMITER_BACKEND=redis` to fail instead.

**Waiting in line:**

- **When there's no room:** the request waits (polling at most every 5s)
  instead of failing. Background jobs wait up to 10 minutes; interactive
  requests wait up to 20s.
- **How the wait is shared between models:** it is split across the remaining
  models in the chain, so a saturated primary still leaves time to fall back.
- **Daily limits don't wait:**
  - a model's daily limit moves straight to the next model;
  - an application budget fails at once, because it applies to every model.

## 4. Retries and error kinds

Adapters map vendor errors to one kind. The gateway decides by kind:

| Kind | Typical cause | Retry same model | Next model | Job re-queued |
|---|---|---|---|---|
| `rate_limited` | 429 | yes | yes | yes |
| `unavailable` | 5xx, overload, timeout, network | yes | yes | yes |
| `model_unavailable` | 404, retired model | no | yes | no |
| `quota_exhausted` | daily or billing quota (Gemini `…PerDay`, OpenAI `insufficient_quota`), or our RPD/TPD | no | yes | no |
| `budget_exhausted` | the application's daily budget | no | **no** | no |
| `auth`, `not_configured` | bad key | no | **no** | no |
| `bad_request` | invalid parameters or schema | no | **no** | no |
| `oversized` | prompt over the model's context or per-request limit (413), or answer cut off at its output cap | no | yes | no |
| `refused`, `bad_output` | safety block, invalid JSON | no | **no** | no |
| (other exception) | application bug | no | **no** | no |

**Backoff:** the delay is `base × 2^retry`, capped at `LLM_RETRY_MAX_DELAY`,
then a random point in its upper half. Retries never happen immediately, and
at most `LLM_MAX_RETRIES` per model.

**Retry-After:** the gateway honors the provider's wait from the
`retry-after(-ms)` header or Google's `RetryInfo.retryDelay`.

- **Shared pause:** that wait is also written as a cooldown, so other workers
  pause too.
- **Waits that are too long:** a wait longer than `LLM_RETRY_MAX_DELAY` moves
  to the next model instead.

**After the gateway gives up:** a still-transient failure re-queues the job
(`JOB_RETRY_DELAYS`, default 30s and 120s, never sooner than Retry-After).
Every one of those retries goes through the quotas again.

## 5. Fallback

**Default chain:**

1. `LLM_PROVIDER`'s model;
2. its same-provider fallback;
3. `LLM_FALLBACKS`, in order.

**Per workflow:** `LLM_ROUTES` replaces the chain for that workflow.

**Skipped models:** any model whose provider has no key.

**What triggers a fallback:** only `rate_limited`, `unavailable`,
`model_unavailable` and `quota_exhausted`. A bad key, a bad request or bad
output fails fast instead of burning other quotas.

**What gets recorded:**

- the job's `provider` and `model` are the model that actually answered;
- `llm_requests.fallback_used` marks fallback answers.

**Embeddings never fall back:** vectors from different models can't be
compared.

## 6. Cache

- **What is cached:** trend analyses and single-query embeddings.
  - Content, strategies and briefs are not cached: regenerating should give a
    new take.
- **Where:** Redis when available, otherwise memory. TTL is
  `LLM_CACHE_TTL_SECONDS`.
- **The key** contains the workflow, the organization and the model chain, plus
  a hash of:
  - the system prompt (prompt version and organization profile);
  - the user prompt (trend, coverage and knowledge passages);
  - the schema and `max_tokens`.
- **Invalidation:** any change to a prompt version, the model, the
  organization's profile or the matching knowledge passages produces a new key.
  Nothing has to be invalidated by hand.
- **Isolation:** the organization id is part of the key, so organization B can
  never read organization A's entry.

## 7. Accounting and observability

- **`llm_requests` table:**
  - one row per provider request, plus one per cache hit with
    `status = 'cached'`;
  - columns: organization, workflow, job, provider, model, status, error
    kind, attempt, retry count, fallback, queue wait, latency, start and end
    times, input/output/total tokens, `usage_unavailable`;
  - tokens are only stored when the provider reported them, never estimated;
  - prompts and outputs are never stored, and error details are truncated.
  - `call_id` groups the attempts of one call; `job_id` links them to
    `ai_generation_jobs`.
- **`GET /api/v1/ai/usage?days=7`** (organization admins): requests,
  successes, failures, cache hits, retries, fallbacks, tokens and average or
  max queue wait, by workflow and model. Add `&job_id=…` to list every request
  one job made: how many requests one analysis generated, on which model, with
  how many retries and tokens, and how long it took.
- **`/health/metrics`** with `METRICS_ENABLED=true`:
  - counters `llm_requests_total`, `llm_requests_success_total`,
    `llm_requests_failed_total{error}`, `llm_rate_limit_total{source}`,
    `llm_retries_total`, `llm_fallback_total`, `llm_cache_hits_total`,
    `llm_input_tokens_total`, `llm_output_tokens_total`;
  - histograms `llm_queue_wait_seconds` and `llm_latency_seconds`;
  - gauge `llm_concurrency`;
  - labels are provider, model and workflow. Organization ids stay out of
    metrics (use the table for those).
  - The counts are per process.
- **Logs:** one `llm_request …` line per request.

Example: everything one trend analysis did:

```sql
SELECT attempt, provider, model, status, error_kind, retry_count, fallback_used,
       queue_wait_ms, latency_ms, input_tokens, output_tokens
FROM llm_requests WHERE job_id = '<ai_generation_jobs.id>' ORDER BY attempt;
```

## 8. What people see

Provider names and raw errors never reach the UI.

| Situation | Message shown |
|---|---|
| Job re-queued | "The AI service is temporarily busy. Your request has been queued and will retry automatically." |
| Daily quota or budget | "AI processing capacity for today has been reached. Please try again later." |
| All models failed | "AI processing is temporarily unavailable. No data was lost. Please try again shortly." |
| Bad key or model | "AI processing isn't set up correctly. Ask an administrator to check it." |

The internal detail goes to the logs and `llm_requests.error_detail`.

**Strategy drafts** fall back to the rule-based draft, with the message above
as the notice.

## 9. When every provider is unavailable

Nothing is lost, and nothing crashes:

- **Trend analysis and briefs:** the job is marked failed with the neutral
  message, after the automatic re-queues. Rule-based estimates stay in place,
  and the UI's "Retry" re-runs it.
- **Post generation:** the job is marked failed in the same way. Existing
  versions are untouched.
- **Strategy drafts:** a rule-based draft is returned.
- **Knowledge search:** keyword-only results.
- **Indexing:** keyword-only results, with a note to re-index later.

## 10. Adding a provider

1. **Adapter:** if the provider speaks OpenAI `/chat/completions`, add a
   `ProviderSpec` with its base URL and key variable to `PROVIDERS` in
   `app/ai/provider.py`. That's all. Otherwise, write an adapter class:
   - attributes `name` and `model`, and
     `generate_structured(system, prompt, schema, max_tokens)`;
   - exactly one request per call;
   - map errors to `AIErrorKind` and pass `retry_after` when known;
   - return `StructuredResult` with the reported token usage.
   
   Then add it to `build_adapter`.
2. **Settings:** add `<provider>_api_key` to `Settings` and the provider name
   to the `LLM_PROVIDER` literal.
3. **Limits:** add `provider/*` (and specific models) to `llm_limits.json`.
4. **Tests:** test the error mapping with `httpx.MockTransport` (see
   `tests/test_llm_gateway.py`).

The gateway, quotas, fallback and accounting need no changes.

## 11. Switching models

- **Automatic:** when the current model reaches a per-minute, per-hour or
  per-day limit (or is down, retired, or can't fit the request), the next
  entry in `LLM_FALLBACKS` takes that request. The earlier model is used again
  as soon as it has room. Order the list by preference.
- **Manual:** change `LLM_PROVIDER` (and optionally `LLM_MODEL`) in `.env`,
  then restart the API and workers. Each provider has defaults, so
  `LLM_PROVIDER=cerebras` alone works.
- **Check what will run:** `cd backend && python -m app.ai.check` prints the
  chain, which keys are present and each model's limits, without sending
  anything. `--probe` sends one tiny request per model to prove the keys and
  models work. Keys are never printed.

## 12. Testing quota behavior locally

- **Automated:** `cd backend && pytest tests/test_llm_gateway.py`.
  - It covers RPM, TPM, RPD, concurrency, budgets, queueing, retries,
    Retry-After, fallback, cache isolation, accounting, and two "workers"
    sharing limits through Redis.
  - It includes the incident: 16 requests in a burst against a 15 RPM model
    never get a 429.
  - Redis tests are skipped when Redis isn't running (`docker compose up -d
    redis`).
- **By hand:**
  1. Set tiny limits, e.g. `LLM_LIMITS='{"gemini/*": {"rpm": 2, "rpd": 5}}'`
     with a real key.
  2. Run a discovery.
  3. Watch the queue form: `queue_wait_ms` in `GET /api/v1/ai/usage`, the
     `llm_request` log lines, or the `llm_requests` table.

## 13. Known limitations

- **Gemini TPD isn't configured by default.** Google reports tokens per minute
  and requests per day; add `tpd` if your tier has one.
- **The memory backend is per process.** Run Redis whenever more than one
  process calls models (Celery workers, or several API replicas).
- **Background waits can occupy a Celery worker.** A background request may
  wait up to `LLM_QUEUE_TIMEOUT_BACKGROUND` inside its worker. Lower it if
  workers are scarce: the job is then re-queued instead.
- **`llm_requests` grows without limit.** Prune old rows periodically, e.g.
  older than 90 days.
- **Streaming is not implemented.** No workflow streams today. When one does,
  add `stream()` to the gateway using the same `acquire`/`release`/`record`
  steps.

## Daily image cap and history retention

AI images go through the same limiter. `backend/llm_limits.json` gives `kie/*` and
`cloudflare/*` a daily `rpd` cap per model (50 and 25, times the safety factor), so one
busy day can't use up a paid balance or the free Cloudflare allowance. When the cap is
reached, the design page says "Today's AI image allowance is used up" and suggests
uploading a design; the provider is not called. Change the cap with
`LLM_LIMITS={"kie/*": {"rpd": 20}}`.

Rows in `llm_requests` older than `LLM_REQUEST_RETENTION_DAYS` (default 90; 0 keeps them)
are deleted once a day, by the in-process scheduler or the `prune_request_history` Celery
beat task.
