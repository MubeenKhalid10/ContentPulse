"""Show (and optionally test) the configured LLM chain.

    python -m app.ai.check            # chain, keys present, limits; no requests
    python -m app.ai.check --probe    # also send one tiny request per model

Keys are never printed. A probe uses one request of each model's quota.
"""

import asyncio
import sys

from app.ai.limits import LimitsCatalog
from app.ai.provider import (
    PROVIDERS,
    AIError,
    LLMTarget,
    api_key_for,
    build_adapter,
    primary_targets,
)
from app.core.config import get_settings

WORKFLOWS = ("trend_alignment", "content_strategy", "post_generation", "design_brief")
SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "score": {"type": "integer"}},
    "required": ["label", "score"],
}


def _limits_text(catalog: LimitsCatalog, target: LLMTarget) -> str:
    limits = catalog.model(target.provider, target.model)
    parts = [
        f"{name}={value}"
        for name in ("rpm", "tpm", "rph", "rpd", "concurrency", "max_output_tokens")
        if (value := getattr(limits, name)) is not None
    ]
    return ", ".join(parts) or "no known limits"


async def _probe(target: LLMTarget) -> str:
    adapter = build_adapter(target, get_settings())
    try:
        result = await adapter.generate_structured(
            system="Rate how relevant a topic is to a B2B software company. Answer in JSON.",
            prompt="Topic: AI agents for finance teams. One-word label, 0-100 score.",
            schema=SCHEMA,
            max_tokens=1500,
        )
    except AIError as exc:
        return f"FAILED ({exc.kind.value}: {exc.message[:120]})"
    return f"ok ({result.input_tokens}+{result.output_tokens} tokens)"


async def main(probe: bool) -> int:
    settings = get_settings()
    catalog = LimitsCatalog.from_settings(settings)
    print(f"LLM_PROVIDER = {settings.llm_provider or '(unset: rule-based)'}")
    print("\nKeys:")
    for name in PROVIDERS:
        print(f"  {name:<11} {'set' if api_key_for(name, settings) else '-'}")

    candidates = [*primary_targets(settings)]
    candidates += [t for v in settings.llm_fallbacks if (t := LLMTarget.parse(v))]
    print("\nModel chain (tried in this order when a limit is reached or a model fails):")
    if not candidates:
        print("  (none: AI is off, the rule-based engines run)")
    seen: list[LLMTarget] = []
    for target in candidates:
        if target in seen:
            continue
        seen.append(target)
        if target.provider not in PROVIDERS:
            status = "SKIPPED: unknown provider"
        elif not api_key_for(target.provider, settings):
            status = f"SKIPPED: no {target.provider.upper()}_API_KEY"
        else:
            status = _limits_text(catalog, target)
        print(f"  {len(seen)}. {target}  [{status}]")
    for workflow, chain in settings.llm_routes.items():
        print(f"\nLLM_ROUTES[{workflow}]: {' -> '.join(chain)}")
    if not settings.llm_fallback_enabled:
        print("\nLLM_FALLBACK_ENABLED=false: only the first model is used.")

    if probe:
        print("\nProbing (one small request each):")
        failures = 0
        for target in seen:
            if target.provider in PROVIDERS and api_key_for(target.provider, settings):
                outcome = await _probe(target)
                failures += outcome.startswith("FAILED")
                print(f"  {target}: {outcome}")
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--probe" in sys.argv)))
