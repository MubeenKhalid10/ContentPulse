import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import DesignBriefStatus, JobStatus, Platform, PostStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
DesignFormat = Literal["text_only", "single_image", "carousel", "infographic", "video", "reel"]


class Person(BaseModel):
    id: uuid.UUID
    name: str | None
    email: str


class TaskPost(BaseModel):
    id: uuid.UUID
    title: str | None
    platform: Platform
    status: PostStatus
    current_version: int
    topic_title: str | None


class TaskListItem(BaseModel):
    id: uuid.UUID
    status: DesignBriefStatus
    format: str
    dimensions: str | None
    headline: str | None
    post: TaskPost
    assignee: Person | None
    creative_versions: int
    source: str
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class TaskPage(BaseModel):
    items: list[TaskListItem]
    total: int
    counts: dict[str, int]


class CreativeFile(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int | None
    position: int
    url: str  # short-lived signed URL for viewing
    download_url: str  # short-lived signed URL that downloads


class CreativeVersion(BaseModel):
    version: int
    note: str | None
    uploaded_by: Person | None
    created_at: datetime
    files: list[CreativeFile]


class PostCopy(BaseModel):
    version: int
    hook: str | None
    body: str | None
    cta: str | None
    hashtags: list[str]
    # Blog posts: SEO title, meta description, slug, keywords.
    blog: dict | None = None


class BrandGuidelines(BaseModel):
    brand_voice: str | None
    tone: str | None
    colors: list[str]
    typography: str | None
    content_guidelines: str | None
    forbidden_terms: list[str]


class ReviewComment(BaseModel):
    body: str
    kind: str
    author: Person | None
    post_version: int
    creative_version: int | None
    created_at: datetime


class ReviewSummary(BaseModel):
    """The latest approval round for a post, for the people revising it."""

    request_id: uuid.UUID
    status: str
    round: int
    post_version: int
    creative_version: int | None
    reviewer: Person | None
    reviewed_at: datetime | None
    comments: list[ReviewComment]


class ImageJob(BaseModel):
    status: JobStatus
    error: str | None
    version: int | None


class TaskDetail(TaskListItem):
    visual_concept: str | None
    supporting_text: str | None
    slide_structure: list[str]
    visual_elements: list[str]
    brand_requirements: dict
    cta: str | None
    designer_notes: str | None
    content: PostCopy | None
    brand: BrandGuidelines
    creatives: list[CreativeVersion]
    storage: Literal["s3", "local"]
    max_upload_mb: int
    allowed_types: list[str]
    ai_brief_pending: bool
    # "Generate image with AI": whether a provider is set up, and the latest job.
    ai_images: bool = False
    image_job: ImageJob | None = None
    review: ReviewSummary | None = None


class BriefUpdate(BaseModel):
    format: DesignFormat | None = None
    dimensions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = (
        None
    )
    visual_concept: Text | None = None
    headline: Text | None = None
    supporting_text: Text | None = None
    slide_structure: Annotated[list[Item], Field(max_length=20)] | None = None
    visual_elements: Annotated[list[Item], Field(max_length=20)] | None = None
    cta: Text | None = None
    designer_notes: Text | None = None


class AssignRequest(BaseModel):
    # A designer may only assign themselves; null unassigns (design managers).
    assignee_id: uuid.UUID | None


class UploadRequest(BaseModel):
    file_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    file_type: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    file_size: Annotated[int, Field(ge=1)]


class UploadTicket(BaseModel):
    url: str
    method: str
    headers: dict[str, str]
    storage_key: str
    expires_at: datetime


class UploadedFile(BaseModel):
    storage_key: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    file_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]


class RegisterAssets(BaseModel):
    """Spec §41 POST /design/tasks/{id}/assets: the files just uploaded, in
    display order, become the next creative version."""

    files: Annotated[list[UploadedFile], Field(min_length=1, max_length=20)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
