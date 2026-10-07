from enum import StrEnum

from app.core.permissions import Role  # noqa: F401  (re-exported for models)


class MemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class AuthProvider(StrEnum):
    LOCAL = "local"
    SUPABASE = "supabase"


class Platform(StrEnum):
    LINKEDIN = "linkedin"
    X = "x"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    # Long-form articles: a content style for the website, never auto-published.
    BLOG = "blog"


class TrendFrequency(StrEnum):
    MANUAL = "manual"
    HOURLY = "hourly"
    EVERY_6_HOURS = "every_6_hours"
    DAILY = "daily"


class OfferingKind(StrEnum):
    """organization_services rows cover services, products and expertise (spec §2)."""

    SERVICE = "service"
    PRODUCT = "product"
    EXPERTISE = "expertise"


class CrawlStatus(StrEnum):
    PENDING = "pending"
    CRAWLING = "crawling"
    EXTRACTED = "extracted"
    EMBEDDED = "embedded"
    FAILED = "failed"


class KnowledgeJobKind(StrEnum):
    CRAWL = "crawl"
    REINDEX = "reindex"


class KnowledgeJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self in (KnowledgeJobStatus.QUEUED, KnowledgeJobStatus.RUNNING)


class DiscoveryRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class SourceHealth(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    DOWN = "down"


class TrendStatus(StrEnum):
    NEW = "new"
    ANALYZED = "analyzed"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class RelevanceLevel(StrEnum):
    HIGHLY_RELEVANT = "highly_relevant"
    RELEVANT = "relevant"
    WEAKLY_RELEVANT = "weakly_relevant"
    NOT_RELEVANT = "not_relevant"


class TopicStatus(StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class PostStatus(StrEnum):
    DRAFT = "draft"
    CONTENT_REVIEW = "content_review"
    DESIGN_PENDING = "design_pending"
    DESIGN_IN_PROGRESS = "design_in_progress"
    DESIGN_UPLOADED = "design_uploaded"
    PENDING_APPROVAL = "pending_approval"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    FINAL = "final"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class VersionSource(StrEnum):
    AI = "ai"
    MANUAL = "manual"


class DesignBriefStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
