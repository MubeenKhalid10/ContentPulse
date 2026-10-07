"""Backend-enforced state machines (spec §54, engineering rule 5).

The frontend never sets a status directly; every status change goes through
these transition tables, and invalid moves raise INVALID_STATE_TRANSITION.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransition
from app.models.design import CreativeAsset
from app.models.enums import PostStatus, StrategyStatus, TopicStatus, TrendStatus
from app.models.post import Post
from app.services import audit


class StateMachine[S: StrEnum]:
    def __init__(self, entity: str, transitions: Mapping[S, Iterable[S]]) -> None:
        self.entity = entity
        self._transitions = {state: frozenset(targets) for state, targets in transitions.items()}

    def allowed(self, current: S) -> list[S]:
        return sorted(self._transitions.get(current, frozenset()))

    def can(self, current: S, target: S) -> bool:
        return target in self._transitions.get(current, frozenset())

    def assert_can(self, current: S, target: S) -> None:
        if not self.can(current, target):
            raise InvalidStateTransition(
                f"A {self.entity} in status '{current}' cannot move to '{target}'.",
                details={
                    "from": current.value,
                    "to": target.value,
                    "allowed": [s.value for s in self.allowed(current)],
                },
            )


_P = PostStatus
POST_MACHINE: StateMachine[PostStatus] = StateMachine(
    "post",
    {
        _P.DRAFT: {_P.DESIGN_PENDING, _P.ARCHIVED},
        # Legacy: the review step was removed; old rows were moved to draft.
        _P.CONTENT_REVIEW: {_P.DRAFT, _P.DESIGN_PENDING, _P.ARCHIVED},
        _P.DESIGN_PENDING: {_P.DESIGN_IN_PROGRESS, _P.DESIGN_UPLOADED, _P.DRAFT, _P.ARCHIVED},
        _P.DESIGN_IN_PROGRESS: {_P.DESIGN_UPLOADED, _P.DESIGN_PENDING, _P.ARCHIVED},
        _P.DESIGN_UPLOADED: {_P.PENDING_APPROVAL, _P.DESIGN_IN_PROGRESS, _P.ARCHIVED},
        _P.PENDING_APPROVAL: {_P.APPROVED, _P.CHANGES_REQUESTED, _P.REJECTED},
        # Revisions may touch the creative or the copy.
        _P.CHANGES_REQUESTED: {
            _P.DESIGN_IN_PROGRESS,
            _P.DESIGN_UPLOADED,
            _P.DRAFT,
            _P.ARCHIVED,
        },
        _P.APPROVED: {_P.FINAL, _P.ARCHIVED},
        _P.FINAL: {_P.ARCHIVED},
        _P.REJECTED: {_P.ARCHIVED},
        _P.ARCHIVED: set(),
    },
)

_T = TopicStatus
TOPIC_MACHINE: StateMachine[TopicStatus] = StateMachine(
    "topic",
    {
        _T.NEW: {_T.REVIEWED, _T.SHORTLISTED, _T.REJECTED, _T.ARCHIVED},
        _T.REVIEWED: {_T.SHORTLISTED, _T.REJECTED, _T.ARCHIVED},
        _T.SHORTLISTED: {_T.REVIEWED, _T.REJECTED, _T.ARCHIVED},
        _T.REJECTED: {_T.REVIEWED, _T.ARCHIVED},
        _T.ARCHIVED: set(),
    },
)

_S = StrategyStatus
STRATEGY_MACHINE: StateMachine[StrategyStatus] = StateMachine(
    "strategy",
    {
        _S.DRAFT: {_S.APPROVED, _S.ARCHIVED},
        # Reopening an approved strategy returns it to draft for edits.
        _S.APPROVED: {_S.DRAFT, _S.ARCHIVED},
        _S.ARCHIVED: set(),
    },
)

_R = TrendStatus
TREND_MACHINE: StateMachine[TrendStatus] = StateMachine(
    "trend",
    {
        _R.NEW: {_R.ANALYZED, _R.SHORTLISTED, _R.REJECTED, _R.ARCHIVED},
        _R.ANALYZED: {_R.SHORTLISTED, _R.REJECTED, _R.ARCHIVED},
        # Un-shortlisting (from the topic) returns the trend to its analyzed state.
        _R.SHORTLISTED: {_R.ANALYZED, _R.NEW, _R.REJECTED, _R.ARCHIVED},
        # Restoring returns to NEW, or ANALYZED if it was already analyzed.
        _R.REJECTED: {_R.NEW, _R.ANALYZED, _R.ARCHIVED},
        _R.ARCHIVED: set(),
    },
)


async def _has_creative(db: AsyncSession, post: Post) -> bool:
    count = await db.scalar(
        select(func.count()).select_from(CreativeAsset).where(CreativeAsset.post_id == post.id)
    )
    return bool(count)


async def transition_post(
    db: AsyncSession,
    post: Post,
    target: PostStatus,
    *,
    user_id,
) -> None:
    """Move a post to `target`, enforcing the transition table and guards."""
    POST_MACHINE.assert_can(post.status, target)

    if target in {
        PostStatus.DESIGN_UPLOADED,
        PostStatus.PENDING_APPROVAL,
    } and not await _has_creative(db, post):
        raise InvalidStateTransition(
            "This post cannot move forward before a creative is uploaded.",
            details={"from": post.status.value, "to": target.value},
        )

    previous = post.status
    post.status = target
    audit.record(
        db,
        organization_id=post.organization_id,
        user_id=user_id,
        action=audit.AuditAction.STATUS_CHANGED,
        entity_type="post",
        entity_id=post.id,
        old_value={"status": previous},
        new_value={"status": target},
    )
