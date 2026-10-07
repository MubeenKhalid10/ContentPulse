import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DiscoveryRunStatus,
    JobStatus,
    RelevanceLevel,
    RunTrigger,
    SourceHealth,
    TrendStatus,
)
from app.schemas.common import ORMModel, Tag


class DiscoverRequest(BaseModel):
    """Spec §38. Omitted fields use the organization's settings."""

    sources: Annotated[list[Tag], Field(max_length=20)] | None = None
    locations: Annotated[list[Tag], Field(max_length=20)] | None = None


class SourceResult(BaseModel):
    status: Literal["ok", "failed", "not_configured", "running", "unknown"]
    items: int = 0
    error: str | None = None
    error_kind: str | None = None
    mode: str | None = None
    duration_ms: int | None = None


class RunRead(ORMModel):
    id: uuid.UUID
    status: DiscoveryRunStatus
    trigger: RunTrigger
    sources: list[str]
    locations: list[str]
    results: dict[str, SourceResult]
    warnings: list[str]
    items_collected: int
    trends_created: int
    trends_updated: int
    mentions_created: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunStarted(BaseModel):
    run_id: uuid.UUID
    status: DiscoveryRunStatus
    run: RunRead


class SourceInfo(BaseModel):
    key: str
    name: str
    description: str
    pricing: Literal["free", "free_tier", "paid", "unavailable"]
    docs_url: str | None
    env_vars: list[str]
    configured: bool
    mode: str | None
    missing: list[str]
    note: str | None
    enabled: bool
    health: SourceHealth
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None


class SourceToggle(BaseModel):
    enabled: bool


class Signal(BaseModel):
    score: int
    detail: str


class TrendListItem(ORMModel):
    id: uuid.UUID
    topic: str
    title: str | None
    description: str | None
    keywords: list[str]
    category: str | None
    locations: list[str]
    sources: list[str]
    status: TrendStatus
    first_seen_at: datetime
    last_seen_at: datetime
    mention_count: int
    opportunity_score: float | None
    signals: dict[str, Signal]
    relevance_level: RelevanceLevel | None
    relevance_overridden: bool = False
    analyzed_at: datetime | None = None


class TrendPage(BaseModel):
    items: list[TrendListItem]
    total: int


class MentionRead(ORMModel):
    id: uuid.UUID
    source: str
    title: str | None
    description: str | None
    source_url: str | None
    author: str | None
    location: str | None
    category: str | None
    published_at: datetime | None
    detected_at: datetime
    last_seen_at: datetime | None
    engagement: int | None
    engagement_label: str | None
    growth_indicator: float | None


class AnalysisStatus(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    engine: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class TrendDetail(TrendListItem):
    alignment: dict
    analyzed_at: datetime | None
    relevance_confidence: float | None
    relevance_overridden: bool
    analysis: AnalysisStatus | None
    mentions: list[MentionRead]
    # The topic candidate created from this trend, if any (Sprint 5).
    topic_id: uuid.UUID | None = None


class AnalyzeStarted(BaseModel):
    job_id: uuid.UUID
    status: JobStatus


class RelevanceOverride(BaseModel):
    # null returns control to the analysis.
    relevance_level: RelevanceLevel | None


class AIStatus(BaseModel):
    configured: bool
    engine: Literal["ai", "rules"]
    provider: str | None
    model: str | None
    # Models tried in order ("provider/model"), primary first.
    chain: list[str] = []


class LLMUsageGroup(BaseModel):
    workflow: str
    provider: str
    model: str
    requests: int  # sent to the provider (cache hits excluded)
    succeeded: int
    failed: int
    cached: int
    retries: int
    fallbacks: int
    input_tokens: int
    output_tokens: int
    avg_latency_ms: int | None
    avg_queue_wait_ms: int | None
    max_queue_wait_ms: int


class LLMRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: uuid.UUID
    job_id: uuid.UUID | None
    workflow: str
    provider: str
    model: str
    status: str
    error_kind: str | None
    attempt: int
    retry_count: int
    fallback_used: bool
    queue_wait_ms: int
    latency_ms: int | None
    started_at: datetime
    completed_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    usage_unavailable: bool


class LLMUsage(BaseModel):
    since: datetime
    requests_total: int
    cached_total: int
    groups: list[LLMUsageGroup]
    requests: list[LLMRequestRead]


class MarketOption(BaseModel):
    code: str
    name: str
