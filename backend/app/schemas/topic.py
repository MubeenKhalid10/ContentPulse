import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import Platform, RelevanceLevel, StrategyStatus, TopicStatus
from app.schemas.common import LongText, ORMModel, PatchModel, Tag
from app.schemas.trend import TrendDetail

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text2k = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Heading = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SearchIntent = Literal["informational", "commercial", "transactional", "navigational"]


# --- Topics ------------------------------------------------------------------


class Angle(BaseModel):
    title: str
    angle: str
    platforms: list[str] = []
    evidence: list[str] = []


class PlatformFit(BaseModel):
    platform: Platform
    score: int
    reasons: list[str]
    formats: list[str]


class TopicListItem(ORMModel):
    id: uuid.UUID
    trend_id: uuid.UUID | None
    title: str
    summary: str | None
    relevance_level: RelevanceLevel | None
    matched_services: list[str]
    recommended_platforms: list[Platform]
    status: TopicStatus
    opportunity_score: float | None = None
    strategy_count: int = 0
    approved_strategy_count: int = 0
    created_at: datetime
    updated_at: datetime


class TopicPage(BaseModel):
    items: list[TopicListItem]
    total: int
    # Per-status totals with the other filters applied (for tab badges).
    counts: dict[str, int]


class StrategyDetails(BaseModel):
    """Platform-specific plan beyond the shared strategy fields. Only Blog uses
    it today (its SEO plan); social platforms leave it empty."""

    seo_title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )
    primary_keyword: Keyword | None = None
    secondary_keywords: Annotated[list[Keyword], Field(max_length=15)] = []
    search_intent: SearchIntent | None = None
    outline: Annotated[list[Heading], Field(max_length=15)] = []
    target_word_count: Annotated[int, Field(ge=300, le=6000)] | None = None
    featured_image_direction: Text2k | None = None


class StrategyRead(ORMModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    platform: Platform
    post_type: str
    content_angle: str | None
    objective: str | None
    target_audience: str | None
    hook_direction: str | None
    cta_direction: str | None
    tone: str | None
    recommended_format: str | None
    rationale: str | None
    details: StrategyDetails = Field(default_factory=StrategyDetails)
    source: str
    status: StrategyStatus
    created_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TopicDetail(TopicListItem):
    relevance_reason: str | None
    suggested_angles: list[Angle]
    target_audience: str | None
    platform_fit: list[PlatformFit]
    unsupported_claims: list[str]
    reviewed_at: datetime | None
    trend: TrendDetail | None
    strategies: list[StrategyRead]


class TopicUpdate(PatchModel):
    non_nullable = frozenset({"title"})

    title: Title | None = None
    summary: LongText | None = None
    target_audience: Text2k | None = None


# --- Strategies ---------------------------------------------------------------


class StrategyFields(BaseModel):
    post_type: Short
    content_angle: Text2k | None = None
    objective: Short | None = None
    target_audience: Text2k | None = None
    hook_direction: Text2k | None = None
    cta_direction: Text2k | None = None
    tone: Short | None = None
    recommended_format: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    rationale: Text2k | None = None
    details: StrategyDetails | None = None


class StrategyCreate(StrategyFields):
    platform: Platform
    # Where the draft came from, when it started as a suggestion.
    source: Literal["ai", "rules", "manual"] = "manual"


class StrategyUpdate(PatchModel):
    non_nullable = frozenset({"platform", "post_type"})

    platform: Platform | None = None
    post_type: Short | None = None
    content_angle: Text2k | None = None
    objective: Short | None = None
    target_audience: Text2k | None = None
    hook_direction: Text2k | None = None
    cta_direction: Text2k | None = None
    tone: Short | None = None
    recommended_format: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None
    ) = None
    rationale: Text2k | None = None
    details: StrategyDetails | None = None


class SuggestRequest(BaseModel):
    platform: Platform


class StrategySuggestion(StrategyFields):
    platform: Platform
    source: Literal["ai", "rules"]
    # Why the AI wasn't used, when it fell back to rules.
    notice: str | None = None


# --- Platform rules -----------------------------------------------------------


class PlatformRuleRead(ORMModel):
    platform: Platform
    post_types: list[str]
    objectives: list[str]
    affinity_keywords: list[str]
    tone: str | None
    guidance: str | None
    max_length: int | None
    hashtag_limit: int | None
    updated_at: datetime


class PlatformRuleUpdate(PatchModel):
    non_nullable = frozenset({"post_types", "objectives", "affinity_keywords"})

    post_types: Annotated[list[Short], Field(min_length=1, max_length=20)] | None = None
    objectives: Annotated[list[Short], Field(max_length=20)] | None = None
    affinity_keywords: Annotated[list[Tag], Field(max_length=100)] | None = None
    tone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    guidance: Text2k | None = None
    max_length: Annotated[int, Field(ge=1, le=100_000)] | None = None
    hashtag_limit: Annotated[int, Field(ge=0, le=60)] | None = None
