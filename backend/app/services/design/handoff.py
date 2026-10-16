"""Designer handoff: the design brief as one self-contained document.

A designer who works outside the app (Figma, Canva, an agency) gets everything
about the post in a single file: what it's for, who it's for, the exact copy,
the canvas and export specs for the platform, brand rules and a delivery
checklist. Built on request from the current brief, so it is never stale.
"""

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Platform
from app.models.post import Post
from app.models.topic import ContentStrategy, TopicCandidate
from app.schemas.design import TaskDetail
from app.services.design import service
from app.services.topics.platforms import PLATFORM_LABELS

# What each platform needs from the exported file, and what its UI covers.
PLATFORM_SPECS: dict[Platform, dict[str, str]] = {
    Platform.LINKEDIN: {
        "files": "PNG or JPG for images (under 5 MB each); PDF for carousels (under 100 MB); "
        "MP4 for video.",
        "safe_zone": "Keep key text 60 px from every edge. The feed crops previews to 1.91:1, so "
        "don't put essentials only at the top or bottom of tall images.",
        "tone": "Professional, credible, uncluttered. Readable on a phone without zooming.",
    },
    Platform.X: {
        "files": "PNG or JPG (under 5 MB); MP4 for video. Up to 4 images per post.",
        "safe_zone": "Images are cropped in the timeline. Centre the subject and keep text 8% "
        "from every edge.",
        "tone": "Bold and immediate. One idea per image.",
    },
    Platform.INSTAGRAM: {
        "files": "PNG or JPG (sRGB); MP4 for reels. Carousels up to 10 slides, all the same ratio.",
        "safe_zone": "The grid preview crops to the centre 3:4. Keep text out of the top 14% and "
        "bottom 20% of reels (the app's UI sits there) and 60 px from the edges of posts.",
        "tone": "Visual first, little text. Strong focal point and contrast.",
    },
    Platform.FACEBOOK: {
        "files": "PNG or JPG (under 8 MB); MP4 for video and reels.",
        "safe_zone": "Keep key text 60 px from every edge. Link and feed previews crop, so "
        "centre essentials.",
        "tone": "Friendly and clear. Readable at small sizes.",
    },
    Platform.BLOG: {
        "files": "WebP or JPG under 300 KB for the web; keep a PNG master too. Name the file "
        "with the article slug.",
        "safe_zone": "Used as the featured image and the social share (Open Graph) image: keep "
        "key content inside the centre 1000×500 px and use no text smaller than 40 px.",
        "tone": "Editorial and on-brand. The image should still work without its text.",
    },
}

STEP_PREFIX = re.compile(r"^(?:Slide|Shot|Frame)\s*\d+\s*[:.\-–]\s*", re.I)


def _slug(value: str | None, fallback: str = "post") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:50]
    return slug or fallback


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


def _section(title: str, body: str | None) -> str:
    return f"## {title}\n\n{body.strip()}\n" if body and body.strip() else ""


def _table(rows: list[tuple[str, str | None]]) -> str:
    kept = [(k, v.replace("\n", " ").strip()) for k, v in rows if v and v.strip()]
    return "\n".join(["| | |", "|---|---|", *(f"| **{k}** | {v} |" for k, v in kept)])


def _base_name(t: TaskDetail) -> str:
    return f"{_slug(t.post.title or t.headline)}_{t.post.platform.value}"


def _file_names(t: TaskDetail) -> str:
    base = _base_name(t)
    if t.format in ("carousel", "reel", "video") and t.slide_structure:
        n = len(t.slide_structure)
        names = f"`{base}_v1_01.png` … `{base}_v1_{n:02d}.png`"
        if t.format == "carousel" and t.post.platform == Platform.LINKEDIN:
            names += f" (plus one combined `{base}_v1.pdf`)"
        return names
    return f"`{base}_v1.png`"


async def render(
    db: AsyncSession, organization_id: uuid.UUID, task_id: uuid.UUID
) -> tuple[str, str]:
    """Returns (file name, Markdown)."""
    t = await service.task_detail(db, organization_id, task_id)
    platform = Platform(t.post.platform)
    label = PLATFORM_LABELS[platform]
    spec = PLATFORM_SPECS[platform]
    post = await db.get(Post, t.post.id)
    strategy = (
        await db.get(ContentStrategy, post.content_strategy_id)
        if post and post.content_strategy_id
        else None
    )
    topic = (
        await db.get(TopicCandidate, strategy.topic_id) if strategy and strategy.topic_id else None
    )
    is_blog = platform == Platform.BLOG
    copy = t.content

    title = t.post.title or t.headline or "Untitled post"
    deliverable = t.format.replace("_", " ").capitalize()
    if is_blog:
        deliverable += " (featured image, also the social share image)"
    parts = [
        f"# Design brief: {title}\n",
        _table(
            [
                ("Platform", label),
                ("Deliverable", deliverable),
                ("Canvas", t.dimensions),
                ("Assigned to", (t.assignee.name or t.assignee.email) if t.assignee else None),
            ]
        )
        + "\n",
    ]

    tone = (strategy.tone if strategy else None) or t.brand.tone
    context = [
        f"**Topic:** {topic.title}" if topic else None,
        f"**What the post says:** {strategy.content_angle}"
        if strategy and strategy.content_angle
        else None,
        f"**Goal of the post:** {strategy.objective}" if strategy and strategy.objective else None,
        f"**Audience:** {strategy.target_audience}"
        if strategy and strategy.target_audience
        else None,
        f"**Tone:** {tone}" if tone else None,
        f"**Why this approach:** {strategy.rationale}" if strategy and strategy.rationale else None,
    ]
    parts.append(
        _section("1. What this post is and who it's for", _bullets([c for c in context if c]))
    )

    takeaway = t.headline or ""
    if t.supporting_text:
        takeaway += f"\n\nSupporting line: {t.supporting_text}"
    if t.cta:
        takeaway += f"\n\nWhat we want them to do next: {t.cta}"
    parts.append(_section("2. The one thing the viewer should take away", takeaway))

    if copy:
        text = "\n\n".join(x for x in (copy.hook, copy.body, copy.cta) if x)
        quoted = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
        tags = (
            f"\n\nHashtags (caption only, not on the image): {' '.join(copy.hashtags)}"
            if copy.hashtags
            else ""
        )
        parts.append(
            _section(
                "3. The full post (for context)",
                "Read this first so the visual says the same thing as the words. It's the "
                f"caption, not text to paste into the design.\n\n{quoted}{tags}",
            )
        )

    direction = [
        f"**Visual concept:** {t.visual_concept}" if t.visual_concept else None,
        f"**Hook direction:** {strategy.hook_direction}"
        if strategy and strategy.hook_direction
        else None,
    ]
    parts.append(_section("4. Creative direction", "\n\n".join(d for d in direction if d)))

    if t.slide_structure:
        heading = (
            "Slides"
            if t.format == "carousel"
            else "Shots"
            if t.format in ("reel", "video")
            else "Structure"
        )
        steps = [STEP_PREFIX.sub("", s) for s in t.slide_structure]
        parts.append(
            _section(f"5. {heading}", "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        )
    if t.visual_elements:
        parts.append(_section("6. Visual elements to include", _bullets(t.visual_elements)))

    rules = [
        "Keep on-image text short: about 12 words per slide or frame at most.",
        "Strong visual hierarchy: headline first, supporting line second, logo last.",
        f"Place the logo {t.brand.logo_position.replace('_', ' ')} unless the layout needs it "
        "elsewhere.",
        "Use only claims the post makes; don't add statistics, clients or promises to the visual.",
    ]
    if t.designer_notes:
        rules.insert(0, t.designer_notes.replace("\n", " "))
    parts.append(_section("7. Notes and things to avoid", _bullets(rules)))

    brand = [
        f"**Colours:** {', '.join(t.brand.colors)}" if t.brand.colors else None,
        f"**Typography:** {t.brand.typography}" if t.brand.typography else None,
        f"**Brand voice:** {t.brand.brand_voice}" if t.brand.brand_voice else None,
        f"**Guidelines:** {t.brand.content_guidelines}" if t.brand.content_guidelines else None,
        f"**Never use these words:** {', '.join(t.brand.forbidden_terms)}"
        if t.brand.forbidden_terms
        else None,
        "**Logo:** use the organization's logo file (ask the team if you don't have it).",
    ]
    parts.append(_section("8. Brand", _bullets([b for b in brand if b])))

    parts.append(
        _section(
            f"9. Export guide for {label}",
            _bullets(
                [
                    f"**Canvas:** {t.dimensions}"
                    if t.dimensions
                    else "**Canvas:** as set by the deliverable above.",
                    f"**File type:** {spec['files']}",
                    f"**Safe zone:** {spec['safe_zone']}",
                    "**Colour:** sRGB at the exact pixel size. Don't upscale.",
                    f"**Look and feel:** {spec['tone']}",
                    f"**File names:** {_file_names(t)}. Use `v2`, `v3` for each revision.",
                    "**Source:** outline fonts in exports, and keep an editable source file "
                    "(Figma link, PSD, AI) for later edits.",
                ]
            ),
        )
    )

    checklist = (
        "Matches the exact canvas size.",
        "Text is readable on a phone and nothing sits in the safe-zone margins.",
        "Headline matches the brief; no extra claims added.",
        "Brand colours, typography and logo are applied.",
        "Exported files follow the naming above.",
        "Alt text written (one sentence describing the image).",
        "Files uploaded on the task page with a short note, then submitted for review.",
    )
    todo = "\n".join(f"- [ ] {c}" for c in checklist)
    parts.append(_section("10. Before you hand it back", todo))

    return (
        f"design-brief-{_base_name(t)}.md",
        "\n".join(p for p in parts if p).rstrip() + "\n",
    )
