"""Import every model so Base.metadata is complete (Alembic, tests)."""

from app.models.ai import AIGenerationJob, LLMRequest, PromptTemplate
from app.models.approval import ApprovalComment, ApprovalRequest
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.design import CreativeAsset, DesignBrief
from app.models.knowledge import KnowledgeChunk, KnowledgeCrawlJob, KnowledgeDocument
from app.models.organization import (
    BrandProfile,
    Organization,
    OrganizationMember,
    OrganizationService,
    OrganizationSettings,
)
from app.models.post import Post, PostVersion
from app.models.topic import ContentStrategy, PlatformRule, TopicCandidate
from app.models.trend import Trend, TrendDiscoveryRun, TrendMention, TrendSource
from app.models.user import User

__all__ = [
    "AIGenerationJob",
    "ApprovalComment",
    "ApprovalRequest",
    "AuditLog",
    "Base",
    "BrandProfile",
    "ContentStrategy",
    "CreativeAsset",
    "DesignBrief",
    "LLMRequest",
    "KnowledgeChunk",
    "KnowledgeCrawlJob",
    "KnowledgeDocument",
    "Organization",
    "OrganizationMember",
    "OrganizationService",
    "OrganizationSettings",
    "PlatformRule",
    "Post",
    "PostVersion",
    "PromptTemplate",
    "TopicCandidate",
    "Trend",
    "TrendDiscoveryRun",
    "TrendMention",
    "TrendSource",
    "User",
]
