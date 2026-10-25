"""Compare models on trend alignment against human labels.

    uv run python -m app.ai.eval_alignment \
        --models groq/qwen/qwen3.8-27b,groq/openai/gpt-oss-120b [--labels labels.json]
        [--organization <uuid>] [--limit 40] [--out results.json]

Labels: a JSON list of {"trend_id": "...", "label": "relevant"} (labels are
highly_relevant | relevant | weakly_relevant | not_relevant). Without
--labels, trends whose relevance someone overrode in the app are the labeled
set. Every model sees the same prompt the app sends (organization profile,
coverage, knowledge passages). Calls go through the gateway uncached, under
workflow "alignment_eval", so they are rate limited and priced like real ones.

Reports per model: exact accuracy, accuracy within one level, how often it
over-rates a trend (the costly mistake), failures, tokens and cost, then how
often the models agree with each other.
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.ai.gateway import LLMGateway
from app.ai.pricing import cost_usd
from app.ai.provider import AIError, AIErrorKind, LLMTarget, build_adapter
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.enums import RelevanceLevel
from app.models.trend import Trend
from app.services.alignment.context import load_context
from app.services.alignment.engines import retrieve_passages, top_mentions, trend_prompt
from app.services.alignment.result import InvalidAlignment, parse_ai_output, response_schema

LEVELS = [
    RelevanceLevel.NOT_RELEVANT,
    RelevanceLevel.WEAKLY_RELEVANT,
    RelevanceLevel.RELEVANT,
    RelevanceLevel.HIGHLY_RELEVANT,
]
RANK = {level: i for i, level in enumerate(LEVELS)}


@dataclass
class Score:
    target: str
    answers: dict[uuid.UUID, RelevanceLevel] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal | None = Decimal(0)


async def _labels(path: str | None, organization: uuid.UUID | None, limit: int):
    if path:
        rows = json.loads(await asyncio.to_thread(Path(path).read_text, encoding="utf-8"))
        return {uuid.UUID(r["trend_id"]): RelevanceLevel(r["label"]) for r in rows[:limit]}
    async with SessionLocal() as db:
        query = select(Trend.id, Trend.relevance_level).where(
            Trend.relevance_overridden.is_(True), Trend.relevance_level.is_not(None)
        )
        if organization:
            query = query.where(Trend.organization_id == organization)
        rows = await db.execute(query.order_by(Trend.last_seen_at.desc()).limit(limit))
        return {r.id: RelevanceLevel(r.relevance_level) for r in rows}


async def _cases(trend_ids):
    """The exact system prompt, user prompt and schema the app would send."""
    from app.ai import prompts

    template = prompts.load("organization_alignment")
    cases = []
    async with SessionLocal() as db:
        for trend_id in trend_ids:
            trend = await db.get(Trend, trend_id)
            if trend is None:
                print(f"skip {trend_id}: no such trend", file=sys.stderr)
                continue
            ctx = await load_context(db, trend.organization_id)
            mentions = await top_mentions(db, trend.id)
            passages = await retrieve_passages(db, trend.organization_id, trend)
            cases.append(
                {
                    "trend": trend,
                    "ctx": ctx,
                    "passages": passages,
                    "system": template.render(
                        organization_name=ctx.name, organization_profile=ctx.profile_text
                    ),
                    "prompt": trend_prompt(trend, mentions, passages),
                    "schema": response_schema(ctx.platforms),
                }
            )
    return cases


async def _run_model(target: LLMTarget, cases) -> Score:
    settings = get_settings()
    gateway = LLMGateway([build_adapter(target, settings)], settings)
    score = Score(str(target))
    for case in cases:
        trend = case["trend"]
        try:
            raw = await gateway.generate_structured(
                system=case["system"],
                prompt=case["prompt"],
                schema=case["schema"],
                max_tokens=2000,
                workflow="alignment_eval",
                organization_id=trend.organization_id,
            )
            parsed = parse_ai_output(
                raw.data,
                service_names=case["ctx"].service_names,
                passages=case["passages"],
                platforms=case["ctx"].platforms,
            )
        except (AIError, InvalidAlignment) as exc:
            kind = exc.kind.value if isinstance(exc, AIError) else AIErrorKind.BAD_OUTPUT.value
            score.failures[kind] = score.failures.get(kind, 0) + 1
            continue
        score.answers[trend.id] = parsed.classification
        score.input_tokens += raw.input_tokens or 0
        score.output_tokens += raw.output_tokens or 0
        price = cost_usd(
            target.provider,
            target.model,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            cached_input_tokens=raw.cached_input_tokens,
        )
        score.cost = None if price is None or score.cost is None else score.cost + price
    return score


def _report(labels, scores: list[Score]) -> dict:
    out = {"labeled": len(labels), "models": []}
    for s in scores:
        answered = [t for t in labels if t in s.answers]
        exact = sum(s.answers[t] == labels[t] for t in answered)
        near = sum(abs(RANK[s.answers[t]] - RANK[labels[t]]) <= 1 for t in answered)
        over = sum(RANK[s.answers[t]] > RANK[labels[t]] for t in answered)
        n = len(answered) or 1
        out["models"].append(
            {
                "model": s.target,
                "answered": len(answered),
                "failures": s.failures,
                "exact_accuracy": round(exact / n, 3),
                "within_one_level": round(near / n, 3),
                "over_rated": round(over / n, 3),
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "cost_usd": float(s.cost) if s.cost is not None else None,
                "cost_usd_per_trend": (
                    round(float(s.cost) / len(answered), 6)
                    if s.cost is not None and answered
                    else None
                ),
            }
        )
    if len(scores) >= 2:
        a, b = scores[0], scores[1]
        both = [t for t in labels if t in a.answers and t in b.answers]
        out["agreement"] = {
            "models": [a.target, b.target],
            "compared": len(both),
            "same_level": round(
                sum(a.answers[t] == b.answers[t] for t in both) / (len(both) or 1), 3
            ),
        }
    return out


async def main(args) -> int:
    targets = [LLMTarget.parse(m) for m in args.models.split(",")]
    if not all(targets) or len(targets) < 1:
        print("--models takes provider/model entries, comma-separated", file=sys.stderr)
        return 2
    labels = await _labels(
        args.labels, uuid.UUID(args.organization) if args.organization else None, args.limit
    )
    if not labels:
        print(
            "No labeled trends. Override some trends' relevance in the app, or pass --labels.",
            file=sys.stderr,
        )
        return 1
    cases = await _cases(list(labels))
    print(f"{len(cases)} labeled trends; {len(targets)} models", file=sys.stderr)
    scores = [await _run_model(t, cases) for t in targets]
    report = _report(labels, scores)
    for m in report["models"]:
        print(
            f"{m['model']:<40} exact {m['exact_accuracy']:.0%}  ±1 {m['within_one_level']:.0%}  "
            f"over-rated {m['over_rated']:.0%}  answered {m['answered']}  "
            f"failures {m['failures'] or 0}  tokens {m['input_tokens']}/{m['output_tokens']}  "
            f"cost ${m['cost_usd'] if m['cost_usd'] is not None else '?'}"
        )
    if "agreement" in report:
        print(f"agreement: {report['agreement']['same_level']:.0%} same level")
    if args.out:
        await asyncio.to_thread(
            Path(args.out).write_text, json.dumps(report, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", required=True)
    parser.add_argument("--labels")
    parser.add_argument("--organization")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--out")
    sys.exit(asyncio.run(main(parser.parse_args())))
