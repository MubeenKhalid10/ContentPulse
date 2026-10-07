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
