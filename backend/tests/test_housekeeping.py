import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.ai import LLMRequest
from app.services.housekeeping import prune_llm_requests


def _row(age_days: int) -> LLMRequest:
    when = datetime.now(UTC) - timedelta(days=age_days)
    return LLMRequest(
        call_id=uuid.uuid4(),
        workflow="test",
        provider="fake",
        model="m",
        status="succeeded",
        started_at=when,
        created_at=when,
    )


async def test_old_request_history_is_pruned(db):
    db.add_all([_row(200), _row(91), _row(30), _row(0)])
    await db.commit()

    assert await prune_llm_requests() == 2
    remaining = await db.scalar(select(func.count()).select_from(LLMRequest))
    assert remaining == 2


async def test_retention_zero_keeps_everything(db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_request_retention_days", 0)
    db.add(_row(400))
    await db.commit()
    assert await prune_llm_requests() == 0
