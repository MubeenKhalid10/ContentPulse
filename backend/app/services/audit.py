"""Audit trail (spec §34). Entries join the caller's transaction."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditAction(StrEnum):
    ORGANIZATION_CREATED = "ORGANIZATION_CREATED"
    ORGANIZATION_UPDATED = "ORGANIZATION_UPDATED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    BRAND_UPDATED = "BRAND_UPDATED"
    SERVICE_CREATED = "SERVICE_CREATED"
    SERVICE_UPDATED = "SERVICE_UPDATED"
    SERVICE_DELETED = "SERVICE_DELETED"
    MEMBER_INVITED = "MEMBER_INVITED"
    MEMBER_JOINED = "MEMBER_JOINED"
    MEMBER_UPDATED = "MEMBER_UPDATED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    KNOWLEDGE_CRAWL_STARTED = "KNOWLEDGE_CRAWL_STARTED"
    KNOWLEDGE_CRAWL_CANCELLED = "KNOWLEDGE_CRAWL_CANCELLED"
    KNOWLEDGE_REINDEX_STARTED = "KNOWLEDGE_REINDEX_STARTED"
    KNOWLEDGE_DOCUMENT_ADDED = "KNOWLEDGE_DOCUMENT_ADDED"
    KNOWLEDGE_DOCUMENT_UPDATED = "KNOWLEDGE_DOCUMENT_UPDATED"
    KNOWLEDGE_DOCUMENT_DELETED = "KNOWLEDGE_DOCUMENT_DELETED"
    TREND_DISCOVERY_STARTED = "TREND_DISCOVERY_STARTED"
    TREND_SHORTLISTED = "TREND_SHORTLISTED"
    TREND_REJECTED = "TREND_REJECTED"
    TREND_RESTORED = "TREND_RESTORED"
    TREND_ANALYSIS_REQUESTED = "TREND_ANALYSIS_REQUESTED"
    TREND_RELEVANCE_OVERRIDDEN = "TREND_RELEVANCE_OVERRIDDEN"
    STATUS_CHANGED = "STATUS_CHANGED"
    TOPIC_SHORTLISTED = "TOPIC_SHORTLISTED"
    TOPIC_REVIEWED = "TOPIC_REVIEWED"
    TOPIC_REJECTED = "TOPIC_REJECTED"
    TOPIC_RESTORED = "TOPIC_RESTORED"
    TOPIC_ARCHIVED = "TOPIC_ARCHIVED"
    TOPIC_UPDATED = "TOPIC_UPDATED"
    STRATEGY_CREATED = "STRATEGY_CREATED"
    STRATEGY_UPDATED = "STRATEGY_UPDATED"
    STRATEGY_APPROVED = "STRATEGY_APPROVED"
    STRATEGY_REOPENED = "STRATEGY_REOPENED"
    STRATEGY_ARCHIVED = "STRATEGY_ARCHIVED"
    PLATFORM_RULES_UPDATED = "PLATFORM_RULES_UPDATED"
    CONTENT_GENERATED = "CONTENT_GENERATED"
    CONTENT_EDITED = "CONTENT_EDITED"
    DESIGN_UPLOADED = "DESIGN_UPLOADED"
    DESIGN_BRIEF_UPDATED = "DESIGN_BRIEF_UPDATED"
    DESIGN_TASK_ASSIGNED = "DESIGN_TASK_ASSIGNED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_COMMENTED = "APPROVAL_COMMENTED"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def diff(obj: Any, changes: dict[str, Any]) -> tuple[dict, dict]:
    """Return (old, new) restricted to fields that actually change."""
    old, new = {}, {}
    for field, value in changes.items():
        current = getattr(obj, field)
        if current != value:
            old[field] = _jsonable(current)
            new[field] = _jsonable(value)
    return old, new


def record(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: AuditAction,
    entity_type: str,
    entity_id: uuid.UUID | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        action=action.value,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=_jsonable(old_value) if old_value is not None else None,
        new_value=_jsonable(new_value) if new_value is not None else None,
    )
    db.add(entry)
    return entry
