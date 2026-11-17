"""Retire the "archived" status: Rejected replaces it

Revision ID: f2a9c4e6b318
Revises: e5c8a3b7d192
Create Date: 2026-11-17 12:00:00.000000

Nothing can archive any more. Rows already archived move to where they would be
found now: trends, topics and posts to rejected (restorable from the Rejected
tab), plans back to draft. The enum types keep the "archived" value: Postgres
can't drop an enum value without rebuilding the type.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2a9c4e6b318"
down_revision: str | None = "e5c8a3b7d192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("trends", "topic_candidates", "posts"):
        op.execute(f"UPDATE {table} SET status = 'rejected' WHERE status = 'archived'")
    op.execute("UPDATE content_strategies SET status = 'draft' WHERE status = 'archived'")


def downgrade() -> None:
    # Which rows were archived before isn't recorded; nothing to restore.
    pass
