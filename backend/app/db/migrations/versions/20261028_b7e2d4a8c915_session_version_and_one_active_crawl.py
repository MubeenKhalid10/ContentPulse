"""session version on users, and one active knowledge job per organization

Revision ID: b7e2d4a8c915
Revises: a3c9e1f5b762
Create Date: 2026-10-28 10:00:00.000000

users.token_version: local-auth sessions carry it, so a password change, a
reset or a logout can end every session already issued. Existing sessions have
no version and count as 0, which is every user's starting value: nobody is
signed out by this migration.

The partial unique index makes "one queued/running crawl per organization" a
database guarantee. An older duplicate is closed the way the app's own
stale-job recovery closes a dead one.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d4a8c915"
down_revision: str | None = "a3c9e1f5b762"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_knowledge_crawl_jobs_one_active"


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.execute(
        """
        UPDATE knowledge_crawl_jobs AS j
        SET status = 'failed',
            error = 'Interrupted: superseded by a newer job.',
            finished_at = now()
        WHERE j.status IN ('queued', 'running')
          AND EXISTS (
            SELECT 1 FROM knowledge_crawl_jobs AS newer
            WHERE newer.organization_id = j.organization_id
              AND newer.status IN ('queued', 'running')
              AND (newer.created_at, newer.id) > (j.created_at, j.id)
          )
        """
    )
    op.create_index(
        INDEX,
        "knowledge_crawl_jobs",
        ["organization_id"],
        unique=True,
        postgresql_where="status IN ('queued', 'running')",
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="knowledge_crawl_jobs")
    op.drop_column("users", "token_version")
