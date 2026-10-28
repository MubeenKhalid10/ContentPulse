from datetime import UTC, datetime


def utcnow() -> datetime:
    """The current time, timezone-aware (UTC)."""
    return datetime.now(UTC)
