"""Blog (long-form article) playbook: the SEO plan on its strategy, the
structured output contract for its copy, checks and the no-LLM template.

A blog post reuses the shared post fields so versioning, design and approval
work unchanged: `hook` is the introduction, `body` is Markdown with `##`
sections ending in a conclusion, `cta` is the call to action. The SEO fields
(title, meta title/description, slug, keywords) live in the version's
metadata under "blog". Blog content is never published automatically.
"""

import re
import unicodedata
from typing import Any, get_args

from app.models.topic import TopicCandidate
from app.schemas.topic import SearchIntent
from app.services.content.copy import CITATION, InvalidCopy, PostCopy

DESIGN_FORMAT = "single_image"  # the featured image
META_TITLE_MAX = 60
META_DESCRIPTION_MAX = 160
MIN_WORDS = 600
INTENTS = get_args(SearchIntent)
HEADING = re.compile(r"^#{2,3}\s+\S", re.M)
WORD = re.compile(r"\b\w+\b")


def slugify(text: str | None, limit: int = 80) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0]
    return slug


def _text(raw: dict[str, Any], key: str, limit: int) -> str | None:
    return str(raw.get(key) or "").strip()[:limit] or None


def _items(raw: dict[str, Any], key: str, limit: int, count: int) -> list[str]:
    values = [str(x).strip()[:limit] for x in raw.get(key) or [] if str(x).strip()]
    return list(dict.fromkeys(values))[:count]


# --- Strategy: the SEO plan ------------------------------------------------------------


def plan_schema() -> dict[str, Any]:
    def text(description: str) -> dict[str, Any]:
        return {"type": "string", "description": description}

    fields = {
        "seo_title": text("Working SEO title, under 70 characters, with the primary keyword."),
        "primary_keyword": text("The search phrase the article should rank for."),
        "secondary_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 related search phrases.",
        },
        "search_intent": {"type": "string", "enum": list(INTENTS)},
        "outline": {
            "type": "array",
            "items": {"type": "string"},
            "description": "4-7 H2 section headings, in order, before the conclusion.",
        },
        "target_word_count": {"type": "integer", "description": "Between 800 and 2500."},
        "featured_image_direction": text("What the featured image should show."),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }


def clean_plan(raw: Any) -> dict[str, Any]:
    """Tolerant cleanup of a model-written plan (stored in strategy.details)."""
    raw = raw if isinstance(raw, dict) else {}
    intent = (_text(raw, "search_intent", 40) or "").lower()
    try:
        words = int(raw.get("target_word_count") or 0)
    except (TypeError, ValueError):
        words = 0
    plan = {
        "seo_title": _text(raw, "seo_title", 120),
        "primary_keyword": _text(raw, "primary_keyword", 80),
        "secondary_keywords": _items(raw, "secondary_keywords", 80, 15),
        "search_intent": intent if intent in INTENTS else None,
        "outline": _items(raw, "outline", 200, 15),
        "target_word_count": min(6000, max(300, words)) if words else None,
        "featured_image_direction": _text(raw, "featured_image_direction", 2000),
    }
    return {k: v for k, v in plan.items() if v not in (None, [])}


def rules_plan(topic: TopicCandidate, keywords: list[str], audience: str | None) -> dict[str, Any]:
    """A starting SEO plan without an LLM: topic, trend keywords and services."""
    reader = audience or "your audience"
    primary = (keywords[0] if keywords else topic.title)[:80]
    secondary = [k for k in [*keywords[1:6], *topic.matched_services[:3]] if k != primary]
    services = topic.matched_services
    outline = [
        f"What is happening with {topic.title}",
        f"Why it matters for {reader}",
        *([f"Where {services[0]} fits in"] if services else []),
        "Practical steps to take now",
        "Examples in practice",
        "Common mistakes to avoid",
    ]
    return clean_plan(
        {
            "seo_title": f"{topic.title}: What It Means and What to Do Next",
            "primary_keyword": primary,
            "secondary_keywords": secondary,
            "search_intent": "informational",
            "outline": outline,
            "target_word_count": 1500,
            "featured_image_direction": (
                f"A clean, on-brand featured image that captures {topic.title} at a glance. "
                "It doubles as the social share image, so keep text on it minimal."
            ),
        }
    )


def plan_lines(details: dict[str, Any]) -> list[str]:
    """The plan as prompt lines for content generation."""
    words = details.get("target_word_count")
    lines = [
        ("SEO title direction", details.get("seo_title")),
        ("Primary keyword", details.get("primary_keyword")),
        ("Secondary keywords", ", ".join(details.get("secondary_keywords") or [])),
        ("Search intent", details.get("search_intent")),
        ("Target length", f"about {words} words" if words else None),
        ("Featured image direction", details.get("featured_image_direction")),
    ]
    out = [f"{label}: {value}" for label, value in lines if value]
    if outline := details.get("outline"):
        out.append("Outline:\n" + "\n".join(f"- {h}" for h in outline))
    return out


# --- Copy ------------------------------------------------------------------------------


def response_schema() -> dict[str, Any]:
    def text(description: str) -> dict[str, Any]:
        return {"type": "string", "description": description}

    fields = {
        "seo_title": text("The article headline (H1): specific, under 70 characters."),
        "meta_title": text("Title for search results, at most 60 characters."),
        "meta_description": text("Search snippet, 120-160 characters, with the keyword."),
        "slug": text("URL slug: lowercase words joined by hyphens."),
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Primary keyword first, then 2-6 related ones.",
        },
        "introduction": text("The hook and introduction: one or two short paragraphs."),
        "sections": {
            "type": "array",
            "description": "The body sections, in order, before the conclusion.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "body"],
                "properties": {
                    "heading": text("The H2 heading, without '#'."),
                    "body": text(
                        "Markdown paragraphs; '### ' subheadings, lists and examples allowed."
                    ),
                },
            },
        },
        "conclusion": text("The closing section: recap and what it means for the reader."),
        "cta": text("The call to action."),
        "featured_image": text("What the featured image should show."),
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Knowledge passage ids (K1, K2...) the article relies on.",
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }


def compose_body(sections: list[tuple[str, str]], conclusion: str | None) -> str:
    parts = [f"## {heading}\n\n{text}" for heading, text in sections]
    if conclusion:
        parts.append(f"## Conclusion\n\n{conclusion}")
    return "\n\n".join(parts)


def seo_meta(
    *,
    seo_title: str | None,
    meta_title: str | None,
    meta_description: str | None,
    slug: str | None,
    keywords: list[str],
) -> dict[str, Any]:
    title = (seo_title or meta_title or "").strip()[:200] or None
    return {
        "seo_title": title,
        "meta_title": (meta_title or title or "").strip()[:200] or None,
        "meta_description": (meta_description or "").strip()[:400] or None,
        "slug": slugify(slug or title) or None,
        "keywords": list(dict.fromkeys(k.strip()[:80] for k in keywords if k.strip()))[:15],
    }


def parse_output(data: dict[str, Any], *, refs: set[str]) -> PostCopy:
    intro = str(data.get("introduction") or "").strip()
    sections = [
        (str(s.get("heading") or "").strip().lstrip("#").strip()[:200], str(s.get("body") or ""))
        for s in data.get("sections") or []
        if isinstance(s, dict)
    ]
    sections = [(h, b.strip()) for h, b in sections if h and b.strip()]
    if not intro or not sections:
        raise InvalidCopy("The AI returned an article without an introduction or sections.")
    corrections: list[str] = []
    cited = [r for r in data.get("evidence") or [] if r in refs]
    if len(cited) < len(data.get("evidence") or []):
        corrections.append("Removed citations to passages that weren't provided")
    return PostCopy(
        hook=intro,
        body=compose_body(sections, str(data.get("conclusion") or "").strip() or None),
        cta=str(data.get("cta") or "").strip(),
        hashtags=[],
        visual_concept=str(data.get("featured_image") or "").strip() or None,
        design_format=DESIGN_FORMAT,
        evidence=list(dict.fromkeys(cited)),
        corrections=corrections,
        blog=seo_meta(
            seo_title=_text(data, "seo_title", 200),
            meta_title=_text(data, "meta_title", 200),
            meta_description=_text(data, "meta_description", 400),
            slug=_text(data, "slug", 200),
            keywords=[str(k) for k in data.get("keywords") or []],
        ),
    )


def template_copy(
    *,
    topic_title: str,
    relevance_reason: str | None,
    content_angle: str | None,
    audience: str | None,
    cta_direction: str | None,
    keywords: list[str],
    plan: dict[str, Any],
) -> PostCopy:
    """A structured article skeleton when no AI model is configured: the
    strategy's outline with the analysis filled in, for a writer to finish."""
    reader = audience or "your readers"
    reason = CITATION.sub("", relevance_reason or "").strip()
    outline = plan.get("outline") or [
        f"What is happening with {topic_title}",
        f"Why it matters for {reader}",
        "Practical steps to take now",
    ]
    known = [p for p in (content_angle, reason) if p]
    sections = [
        (
            heading,
            known[i]
            if i < len(known)
            else f"Explain {heading[0].lower() + heading[1:]}, with a concrete example from "
            f"your own work that {reader} will recognize.",
        )
        for i, heading in enumerate(outline)
    ]
    title = plan.get("seo_title") or f"{topic_title}: What It Means and What to Do Next"
    description = (content_angle or reason or f"What {topic_title} means for {reader}.").strip()
    return PostCopy(
        hook=(
            f"{topic_title} is changing how {reader} work. This article explains what is "
            "happening, why it matters and the practical steps to take next."
        ),
        body=compose_body(
            sections,
            f"{topic_title} is worth acting on now. Revisit the steps above and start with "
            "the one that fits your situation best.",
        ),
        cta=cta_direction or f"Talk to us about what {topic_title} means for your team.",
        hashtags=[],
        visual_concept=plan.get("featured_image_direction"),
        design_format=DESIGN_FORMAT,
        blog=seo_meta(
            seo_title=title,
            meta_title=title[:META_TITLE_MAX],
            meta_description=description[:META_DESCRIPTION_MAX],
            slug=None,
            keywords=[
                *([plan["primary_keyword"]] if plan.get("primary_keyword") else []),
                *(plan.get("secondary_keywords") or []),
                *keywords,
            ][:8],
        ),
    )


def check_blog(blog: dict[str, Any] | None, hook: str | None, body: str | None) -> list[str]:
    """Blog-specific warnings, shown next to the editor alongside check_copy's."""
    blog = blog or {}
    warnings: list[str] = []
    words = len(WORD.findall(f"{hook or ''} {body or ''}"))
    if words < MIN_WORDS:
        warnings.append(f"About {words:,} words: a blog article usually needs {MIN_WORDS}+.")
    if not HEADING.search(body or ""):
        warnings.append("No section headings: structure the body with '## ' headings.")
    if not blog.get("seo_title"):
        warnings.append("No SEO title.")
    meta_title = blog.get("meta_title") or ""
    if not meta_title:
        warnings.append("No meta title.")
    elif len(meta_title) > META_TITLE_MAX:
        warnings.append(
            f"Meta title is {len(meta_title)} characters; search results show about "
            f"{META_TITLE_MAX}."
        )
    description = blog.get("meta_description") or ""
    if not description:
        warnings.append("No meta description.")
    elif len(description) > META_DESCRIPTION_MAX:
        warnings.append(
            f"Meta description is {len(description)} characters; keep it under "
            f"{META_DESCRIPTION_MAX}."
        )
    if not blog.get("slug"):
        warnings.append("No URL slug.")
    keywords = blog.get("keywords") or []
    if not keywords:
        warnings.append("No target keywords.")
    else:
        primary = keywords[0].casefold()
        searchable = f"{blog.get('seo_title') or ''} {hook or ''}".casefold()
        if primary not in searchable:
            warnings.append(
                f"The primary keyword “{keywords[0]}” isn't in the title or introduction."
            )
    return warnings
