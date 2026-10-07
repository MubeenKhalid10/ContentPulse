"""Post copy (spec §26): the structured output contract, validation of what
the model returns, and checks that run on every version, AI or human."""

import re
from dataclasses import dataclass, field
from typing import Any

DESIGN_FORMATS = ["text_only", "single_image", "carousel", "infographic", "video", "reel"]
HASHTAG = re.compile(r"^#[\w]+$", re.UNICODE)
CITATION = re.compile(r"\s*\[K\d+\]")


def response_schema() -> dict[str, Any]:
    """Structured output only; the frontend never parses model prose."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hook",
            "body",
            "cta",
            "hashtags",
            "visual_concept",
            "design_format",
            "evidence",
        ],
        "properties": {
            "hook": {"type": "string", "description": "The opening line."},
            "body": {
                "type": "string",
                "description": "The main text, without the hook, call to action or hashtags.",
            },
            "cta": {"type": "string", "description": "The closing call to action."},
            "hashtags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hashtags such as #AI, within the playbook's limit.",
            },
            "visual_concept": {
                "type": "string",
                "description": "What the designer should create.",
            },
            "design_format": {"type": "string", "enum": DESIGN_FORMATS},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Knowledge passage ids (K1, K2...) the post relies on.",
            },
        },
    }


@dataclass
class PostCopy:
    hook: str
    body: str
    cta: str
    hashtags: list[str]
    visual_concept: str | None
    design_format: str | None
    evidence: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    # Blog only: SEO title, meta title/description, slug and keywords.
    blog: dict[str, Any] | None = None


class InvalidCopy(ValueError):
    pass


def normalize_hashtags(tags: list[str], limit: int | None) -> tuple[list[str], list[str]]:
    """Clean, de-duplicate and cap hashtags. Returns (hashtags, corrections)."""
    seen: set[str] = set()
    out: list[str] = []
    corrections: list[str] = []
    for raw in tags:
        tag = "#" + re.sub(r"\s+", "", str(raw)).lstrip("#")
        if not HASHTAG.match(tag):
            corrections.append(f"Dropped invalid hashtag {raw!r}")
            continue
        if tag.casefold() in seen:
            continue
        seen.add(tag.casefold())
        out.append(tag)
    if limit is not None and len(out) > limit:
        corrections.append(f"Kept the first {limit} of {len(out)} hashtags (playbook limit)")
        out = out[:limit]
    return out, corrections


def parse_output(data: dict[str, Any], *, refs: set[str], hashtag_limit: int | None) -> PostCopy:
    hook = str(data.get("hook") or "").strip()
    body = str(data.get("body") or "").strip()
    if not hook or not body:
        raise InvalidCopy("The AI returned a post without a hook or body.")
    hashtags, corrections = normalize_hashtags(list(data.get("hashtags") or []), hashtag_limit)
    cited = [r for r in data.get("evidence") or [] if r in refs]
    if len(cited) < len(data.get("evidence") or []):
        corrections.append("Removed citations to passages that weren't provided")
    design_format = data.get("design_format")
    return PostCopy(
        hook=hook,
        body=body,
        cta=str(data.get("cta") or "").strip(),
        hashtags=hashtags,
        visual_concept=str(data.get("visual_concept") or "").strip() or None,
        design_format=design_format if design_format in DESIGN_FORMATS else None,
        evidence=list(dict.fromkeys(cited)),
        corrections=corrections,
    )


def full_text(hook: str | None, body: str | None, cta: str | None, hashtags: list[str]) -> str:
    parts = [p.strip() for p in (hook, body, cta) if p and p.strip()]
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(parts)


def check_copy(
    *,
    hook: str | None,
    body: str | None,
    cta: str | None,
    hashtags: list[str],
    forbidden_terms: list[str],
    max_length: int | None,
    hashtag_limit: int | None,
    platform_label: str,
) -> list[str]:
    """Warnings shown next to the editor. Advisory: people can still save."""
    warnings: list[str] = []
    text = full_text(hook, body, cta, hashtags)
    for term in forbidden_terms:
        if term.strip() and re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.I):
            warnings.append(f"Uses the forbidden term “{term.strip()}”.")
    if max_length and len(text) > max_length:
        warnings.append(
            f"{len(text):,} characters: {len(text) - max_length:,} over the "
            f"{platform_label} limit of {max_length:,}."
        )
    if hashtag_limit is not None and len(hashtags) > hashtag_limit:
        warnings.append(f"{len(hashtags)} hashtags; the playbook allows {hashtag_limit}.")
    if not (cta or "").strip():
        warnings.append("No call to action.")
    return warnings


def template_copy(
    *,
    topic_title: str,
    relevance_reason: str | None,
    content_angle: str | None,
    audience: str | None,
    cta_direction: str | None,
    keywords: list[str],
    hashtag_limit: int | None,
) -> PostCopy:
    """A structured starting point when no AI model is configured. Clearly a
    template: it restates the strategy so a writer can finish it."""
    reason = CITATION.sub("", relevance_reason or "").strip()
    paragraphs = [
        p
        for p in (
            content_angle,
            reason,
            f"What should {audience or 'teams'} do about {topic_title} right now?",
        )
        if p
    ]
    hashtags, _ = normalize_hashtags(
        ["#" + re.sub(r"\W+", "", k.title()) for k in [topic_title, *keywords][:4]],
        hashtag_limit,
    )
    return PostCopy(
        hook=f"{topic_title}: here's what it means for {audience or 'you'}.",
        body="\n\n".join(paragraphs),
        cta=cta_direction or "Tell us how this affects you in the comments.",
        hashtags=hashtags,
        visual_concept=None,
        design_format=None,
    )
