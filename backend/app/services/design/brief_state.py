"""What happens to a post's design brief when the post's review moves.

Every service that moves a post (content, approvals, design) calls these
instead of setting `brief.status` itself, so the rules live in one place:

    submitted for approval   → SUBMITTED
    designer takes it back   → IN_PROGRESS
    approved                 → COMPLETED
    rejected                 → CANCELLED
    changes asked on design  → IN_PROGRESS (same assignee)
    post leaves design       → every open brief CANCELLED

Imports models only, so any service can use it without an import cycle.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.models.design import DesignBrief
from app.models.enums import ApprovalStatus, DesignBriefStatus

B = DesignBriefStatus
OPEN_STATUSES = (B.OPEN, B.ASSIGNED, B.IN_PROGRESS)


def mark_submitted(brief: DesignBrief) -> None:
    brief.status, brief.submitted_at = B.SUBMITTED, utcnow()


def mark_withdrawn(brief: DesignBrief) -> None:
    """The designer took a submitted design back to change it."""
    brief.status, brief.submitted_at = B.IN_PROGRESS, None


def reopen_for_designer(brief: DesignBrief) -> None:
    """Back on the designer's to-do list, with the same assignee."""
    brief.status = B.IN_PROGRESS


def apply_decision(brief: DesignBrief, decision: ApprovalStatus, scope: str) -> None:
    """A design-stage review was decided: finish, cancel or reopen the brief."""
    if decision == ApprovalStatus.APPROVED:
        brief.status = B.COMPLETED
    elif decision == ApprovalStatus.REJECTED:
        brief.status = B.CANCELLED
    elif scope in ("design", "both"):
        reopen_for_designer(brief)


async def cancel_open(db: AsyncSession, post_id: uuid.UUID) -> None:
    """The post left design (back to draft, archived): close its open task."""
    rows = await db.scalars(
        select(DesignBrief).where(
            DesignBrief.post_id == post_id, DesignBrief.status.in_(OPEN_STATUSES)
        )
    )
    for brief in rows:
        brief.status = B.CANCELLED
