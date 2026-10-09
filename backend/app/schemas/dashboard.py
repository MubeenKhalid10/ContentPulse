import uuid
from datetime import datetime

from pydantic import BaseModel


class ActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    user_name: str | None
    created_at: datetime


class TopTrend(BaseModel):
    id: uuid.UUID
    topic: str
    opportunity_score: float | None
    sources: list[str]
    mention_count: int


class DashboardSummary(BaseModel):
    trends_today: int
    relevant_trends: int
    shortlisted_topics: int
    # Topic candidates waiting for a review decision (new or reviewed).
    topics_to_review: int = 0
    drafts: int
    design_pending: int
    pending_approval: int
    approved: int
    top_trends: list[TopTrend]
    recent_activity: list[ActivityItem]


# --- Overview (the dashboard page) --------------------------------------------------


class Metric(BaseModel):
    """A count over the chosen period, the period before it, and a daily series."""

    value: int
    previous: int
    series: list[int]


class TrendingTopic(BaseModel):
    id: uuid.UUID
    topic: str
    source: str | None
    category: str | None
    relevance_level: str | None
    opportunity_score: float | None
    # The growth signal (0-100), shown as momentum: not a percent change.
    momentum: int | None
    why: str | None
    shortlisted: bool


class PostBrief(BaseModel):
    id: uuid.UUID
    title: str | None
    platform: str
    status: str
    updated_at: datetime


class DashboardOverview(BaseModel):
    days: int
    start: datetime
    end: datetime
    trends_discovered: Metric
    relevant_trends: Metric
    posts_generated: Metric
    approved_posts: Metric
    pending_approval: int
    trending: list[TrendingTopic]
    platform_breakdown: dict[str, int]
    pipeline: dict[str, int]
    recent_posts: list[PostBrief]
