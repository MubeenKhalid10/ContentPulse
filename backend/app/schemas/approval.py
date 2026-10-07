import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.models.enums import ApprovalStatus, Platform, PostStatus, RelevanceLevel
from app.schemas.content import VersionRead
from app.schemas.design import CreativeVersion, Person

CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class ApprovalPost(BaseModel):
    id: uuid.UUID
    title: str | None
    platform: Platform
    status: PostStatus
    current_version: int


class ApprovalListItem(BaseModel):
    id: uuid.UUID
    status: ApprovalStatus
    round: int  # 1 for the first submission of this post, 2 after one revision...
    post: ApprovalPost
    topic_title: str | None
    post_version: int
    creative_version: int | None
    preview_url: str | None  # first image of the reviewed creative, signed
    submitted_by: Person | None
    reviewer: Person | None
    comment_count: int
    created_at: datetime
    reviewed_at: datetime | None


class ApprovalPage(BaseModel):
    items: list[ApprovalListItem]
    total: int
    counts: dict[str, int]


class CommentRead(BaseModel):
    id: uuid.UUID
    approval_request_id: uuid.UUID
    post_version: int
    creative_version: int | None
    kind: str
    body: str
    author: Person | None
    created_at: datetime


class TopicContext(BaseModel):
    id: uuid.UUID
    title: str
    relevance_level: RelevanceLevel | None
    relevance_reason: str | None
    trend_id: uuid.UUID | None
    sources: list[str]  # trend sources (spec §53 "Trend source")
    coverage: list[dict]  # a few source links: {title, url, source}


class BriefSummary(BaseModel):
    id: uuid.UUID
    format: str
    dimensions: str | None
    headline: str | None
    visual_concept: str | None
    slide_structure: list[str]
    cta: str | None
    designer_notes: str | None


class Round(BaseModel):
    id: uuid.UUID
    status: ApprovalStatus
    post_version: int
    creative_version: int | None
    submitted_by: Person | None
    reviewer: Person | None
    created_at: datetime
    reviewed_at: datetime | None


class ApprovalDetail(ApprovalListItem):
    content: VersionRead | None  # the copy as submitted (may differ from current)
    copy_changed_since: bool
    creative: CreativeVersion | None  # the creative as submitted
    creatives: list[CreativeVersion]  # all versions, newest first
    versions: list[VersionRead]  # copy history, newest first
    brief: BriefSummary | None
    topic: TopicContext | None
    comments: list[CommentRead]  # every round for this post, oldest first
    rounds: list[Round]
    strategy_id: uuid.UUID | None


class DecisionRequest(BaseModel):
    comment: CommentText | None = None


class ChangesRequest(BaseModel):
    """Spec §42: a reason is required so the revision has direction."""

    comment: CommentText
    # What needs work. Default "both": the creator may revise the copy and
    # upload a new design, then resubmit.
    scope: Literal["design", "copy", "both"] = "both"


class CommentCreate(BaseModel):
    body: CommentText


class ResubmitRequest(BaseModel):
    note: CommentText | None = None
