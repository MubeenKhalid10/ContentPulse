import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import (
    DesignBriefStatus,
    JobStatus,
    Platform,
    PostStatus,
    TopicStatus,
    VersionSource,
)
from app.schemas.blog import BlogMeta
from app.schemas.common import ORMModel
from app.schemas.design import CreativeVersion, ReviewSummary
from app.schemas.topic import StrategyRead

# Blog articles are long-form; platform limits are checked as warnings.
Copy = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60_000)]
Intro = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5_000)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2_000)]
Hashtag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
DesignFormat = Literal["text_only", "single_image", "carousel", "infographic", "video", "reel"]


class GenerateRequest(BaseModel):
    """Spec §40 POST /content/generate, from an approved content strategy."""

    strategy_id: uuid.UUID


class RegenerateRequest(BaseModel):
    # Optional editor instructions, e.g. "shorter, lead with the statistic".
    instructions: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None
    ) = None


class GenerationStatus(BaseModel):
    job_id: uuid.UUID
    kind: str  # generate | regenerate | variant
    status: JobStatus
    engine: str  # ai | template
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class VersionRead(ORMModel):
    id: uuid.UUID
    version_number: int
    hook: str | None
    body: str | None
    cta: str | None
    hashtags: list[str]
    mentions: list[str]
    meta: dict
    source: VersionSource
    change_note: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class TopicRef(BaseModel):
    id: uuid.UUID
    title: str
    status: TopicStatus


class PostListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    platform: Platform
    status: PostStatus
    current_version: int
    hook: str | None
    topic: TopicRef | None
    content_strategy_id: uuid.UUID | None
    variant_of_id: uuid.UUID | None
    generation: GenerationStatus | None
    created_at: datetime
    updated_at: datetime


class PostPage(BaseModel):
    items: list[PostListItem]
    total: int
    counts: dict[str, int]


class Limits(BaseModel):
    max_length: int | None
    hashtag_limit: int | None


class DesignTaskRef(BaseModel):
    id: uuid.UUID
    status: DesignBriefStatus


class PostDetail(PostListItem):
    current: VersionRead | None
    strategy: StrategyRead | None
    variants: list[PostListItem]
    limits: Limits
    editable: bool
    design_task: DesignTaskRef | None = None
    review: ReviewSummary | None = None
    creatives: list[CreativeVersion] = Field(default_factory=list)


class PostUpdate(BaseModel):
    """PATCH creates a new version (spec rule 4); old ones are never changed.
    `base_version` guards against overwriting someone else's newer edit."""

    base_version: int
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
        | None
    ) = None
    hook: Intro | None = None
    body: Copy | None = None
    cta: Line | None = None
    hashtags: Annotated[list[Hashtag], Field(max_length=60)] | None = None
    mentions: Annotated[list[Hashtag], Field(max_length=30)] | None = None
    visual_concept: Line | None = None
    design_format: DesignFormat | None = None
    # Blog posts only: SEO title, meta title/description, slug, keywords.
    blog: BlogMeta | None = None
    change_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )


class RestoreRequest(BaseModel):
    base_version: int
