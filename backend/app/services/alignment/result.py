"""Alignment output (spec §15): JSON schema for the model, and validation that
enforces grounding rules on whatever comes back (spec §71 rules 1-2)."""

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models.enums import RelevanceLevel

Engine = Literal["ai", "rules"]
LEVELS = [level.value for level in RelevanceLevel]
REF = re.compile(r"^K\d+$")


@dataclass
class Passage:
    """A retrieved knowledge chunk, referenced in prompts as K1, K2, ..."""

    ref: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    url: str
    heading: str | None
    content: str
    match: str

    def to_json(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "title": self.title,
            "url": self.url,
            "heading": self.heading,
            "excerpt": self.content[:400],
        }


@dataclass
class Angle:
    title: str
    angle: str
    platforms: list[str]
    evidence: list[str]


@dataclass
class AlignmentResult:
    engine: Engine
    classification: RelevanceLevel
    confidence: float
    organization_fit: int
    audience_relevance: int | None
    matched_services: list[str]
    reason: str
    angles: list[Angle] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    evidence: list[dict[str, str]] = field(default_factory=list)  # {ref, supports}
    # Grounding corrections applied to the model output, kept for debugging.
    corrections: list[str] = field(default_factory=list)

    def to_json(self, passages: list[Passage], **meta: Any) -> dict[str, Any]:
        cited = {e["ref"] for e in self.evidence} | {r for a in self.angles for r in a.evidence}
        return {
            "engine": self.engine,
            "classification": self.classification.value,
            "confidence": self.confidence,
            "organization_fit": self.organization_fit,
            "audience_relevance": self.audience_relevance,
            "matched_services": self.matched_services,
            "reason": self.reason,
            "possible_angles": [asdict(a) for a in self.angles],
            "unsupported_claims": self.unsupported_claims,
            "evidence": self.evidence,
            # Every retrieved passage, cited ones first, so the UI can link [Kn].
            "passages": [p.to_json() for p in sorted(passages, key=lambda p: p.ref not in cited)],
            "corrections": self.corrections,
            **meta,
        }


def response_schema(platforms: list[str]) -> dict[str, Any]:
    """JSON schema for structured output. Ranges live in descriptions because
    numeric constraints aren't supported; values are clamped on validation."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "classification",
            "confidence",
            "organization_fit",
            "audience_relevance",
            "matched_services",
            "reason",
            "possible_angles",
            "unsupported_claims",
            "evidence",
        ],
        "properties": {
            "classification": {"type": "string", "enum": LEVELS},
            "confidence": {
                "type": "number",
                "description": "0 to 1: how sure you are, given the evidence available.",
            },
            "organization_fit": {
                "type": "integer",
                "description": (
                    "0-100: how directly the trend connects to the "
                    "organization's offerings and expertise."
                ),
            },
            "audience_relevance": {
                "type": "integer",
                "description": (
                    "0-100: how much the organization's target audience cares about this trend."
                ),
            },
            "matched_services": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exact names from the organization's services list that "
                    "relate to this trend. Empty if none."
                ),
            },
            "reason": {
                "type": "string",
                "description": (
                    "2-4 sentences on why the trend is or isn't relevant, citing "
                    "passages like [K1]."
                ),
            },
            "possible_angles": {
                "type": "array",
                "description": (
                    "Up to 3 organization-specific content angles. Empty for weak or no relevance."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "angle", "platforms", "evidence"],
                    "properties": {
                        "title": {"type": "string", "description": "A short working title."},
                        "angle": {
                            "type": "string",
                            "description": (
                                "1-2 sentences: the point of view and why this organization "
                                "can credibly make it."
                            ),
                        },
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string", "enum": platforms},
                        },
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Passage ids (K1, K2...) supporting this angle.",
                        },
                    },
                },
            },
            "unsupported_claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tempting claims about the organization that the sources do NOT support."
                ),
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["passage", "supports"],
                    "properties": {
                        "passage": {"type": "string", "description": "A passage id such as K1."},
                        "supports": {"type": "string", "description": "What this passage shows."},
                    },
                },
            },
        },
    }


class InvalidAlignment(ValueError):
    pass


def _clamp_int(value: Any, low: int = 0, high: int = 100) -> int:
    try:
        return max(low, min(high, round(float(value))))
    except (TypeError, ValueError) as exc:
        raise InvalidAlignment(f"not a number: {value!r}") from exc


def parse_ai_output(
    data: dict[str, Any], *, service_names: list[str], passages: list[Passage], platforms: list[str]
) -> AlignmentResult:
    """Validate model output and strip anything ungrounded."""
    corrections: list[str] = []
    try:
        level = RelevanceLevel(data["classification"])
        reason = str(data["reason"]).strip()
        raw_services = list(data["matched_services"])
        raw_angles = list(data["possible_angles"])
        raw_evidence = list(data["evidence"])
        confidence = max(0.0, min(1.0, float(data["confidence"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidAlignment(f"malformed alignment output: {exc}") from exc
    if not reason:
        raise InvalidAlignment("missing reason")

    known_services = {name.casefold(): name for name in service_names}
    matched: list[str] = []
    for name in raw_services:
        canonical = known_services.get(str(name).strip().casefold())
        if canonical and canonical not in matched:
            matched.append(canonical)
        elif not canonical:
            # Spec §18: never claim a service that isn't in the organization context.
            corrections.append(f"Removed unknown service “{name}”")

    refs = {p.ref for p in passages}

    def grounded(items: list[Any]) -> list[str]:
        kept = [str(r).strip() for r in items if str(r).strip() in refs]
        dropped = [str(r) for r in items if str(r).strip() not in refs]
        if dropped:
            corrections.append(f"Removed citations to unknown passages {', '.join(dropped)}")
        return kept

    angles: list[Angle] = []
    if level in (RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT):
        for raw in raw_angles[:3]:
            try:
                title, angle = str(raw["title"]).strip(), str(raw["angle"]).strip()
                chosen = [p for p in raw["platforms"] if p in platforms]
                evidence = grounded(list(raw["evidence"]))
            except (KeyError, TypeError) as exc:
                raise InvalidAlignment(f"malformed angle: {exc}") from exc
            if title and angle:
                angles.append(Angle(title=title, angle=angle, platforms=chosen, evidence=evidence))
    elif raw_angles:
        corrections.append("Dropped angles offered for a weak/irrelevant trend")

    evidence = []
    for item in raw_evidence:
        if isinstance(item, dict) and str(item.get("passage", "")).strip() in refs:
            evidence.append(
                {"ref": str(item["passage"]).strip(), "supports": str(item.get("supports", ""))}
            )
        elif isinstance(item, dict):
            corrections.append(f"Removed evidence citing unknown passage {item.get('passage')}")

    # Citations inside the reason must point at real passages too.
    for ref in set(re.findall(r"\[(K\d+)\]", reason)) - refs:
        reason = reason.replace(f"[{ref}]", "")
        corrections.append(f"Removed citation [{ref}] from reasoning")

    return AlignmentResult(
        engine="ai",
        classification=level,
        confidence=round(confidence, 2),
        organization_fit=_clamp_int(data["organization_fit"]),
        audience_relevance=_clamp_int(data["audience_relevance"]),
        matched_services=matched,
        reason=reason,
        angles=angles,
        unsupported_claims=[
            str(c).strip() for c in data.get("unsupported_claims", []) if str(c).strip()
        ][:8],
        evidence=evidence,
        corrections=corrections,
    )
