"""one pending approval and one active design brief per post

Revision ID: a3c9e1f5b762
Revises: d4f8a2c6e517
Create Date: 2026-10-27 10:00:00.000000

The app keeps at most one open review round and one open design task per post;
these partial unique indexes make that a database guarantee, so a double
click or two admins acting at once can't leave duplicates behind.

Leftovers of an earlier race are cleaned up the way the app does it: an extra
pending approval is dropped (as `withdraw_copy` does) and an extra open design
task is cancelled (as `cancel_briefs` does), keeping the newest of each.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3c9e1f5b762"
down_revision: str | None = "d4f8a2c6e517"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPROVAL_INDEX = "uq_approval_requests_one_pending"
BRIEF_INDEX = "uq_design_briefs_one_active"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM approval_requests AS r
        WHERE r.status = 'pending'
          AND EXISTS (
            SELECT 1 FROM approval_requests AS newer
            WHERE newer.post_id = r.post_id
              AND newer.status = 'pending'
              AND (newer.created_at, newer.id) > (r.created_at, r.id)
          )
        """
    )
    op.create_index(
        APPROVAL_INDEX,
        "approval_requests",
        ["post_id"],
        unique=True,
        postgresql_where="status = 'pending'",
    )
    op.execute(
        """
        UPDATE design_briefs AS b
        SET status = 'cancelled'
        WHERE b.status IN ('open', 'assigned', 'in_progress')
          AND EXISTS (
            SELECT 1 FROM design_briefs AS newer
            WHERE newer.post_id = b.post_id
              AND newer.status IN ('open', 'assigned', 'in_progress')
              AND (newer.created_at, newer.id) > (b.created_at, b.id)
          )
        """
    )
    op.create_index(
        BRIEF_INDEX,
        "design_briefs",
        ["post_id"],
        unique=True,
        postgresql_where="status IN ('open', 'assigned', 'in_progress')",
    )


def downgrade() -> None:
    op.drop_index(BRIEF_INDEX, table_name="design_briefs")
    op.drop_index(APPROVAL_INDEX, table_name="approval_requests")
