"""approval_requests.scope: what a change request opened, stored on the request

Revision ID: c5f1a9d3e728
Revises: b7e2d4a8c915
Create Date: 2026-10-29 10:00:00.000000

The scope of a change request ("copy", "design" or "both") used to be read
back from the audit log. It is business state, so it now lives on the
approval request that was decided. Existing requests are filled in from the
audit entry that recorded their decision; requests with no recorded scope stay
NULL, which the app reads as "both" exactly as before.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5f1a9d3e728"
down_revision: str | None = "b7e2d4a8c915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("scope", sa.String(20), nullable=True))
    op.execute(
        """
        UPDATE approval_requests AS r
        SET scope = a.scope
        FROM (
            SELECT DISTINCT ON (new_value->>'approval_request_id')
                   (new_value->>'approval_request_id')::uuid AS request_id,
                   new_value->>'scope' AS scope
            FROM audit_logs
            WHERE action = 'CHANGES_REQUESTED'
              AND entity_type = 'post'
              AND new_value ? 'scope'
              AND new_value->>'approval_request_id' IS NOT NULL
            ORDER BY new_value->>'approval_request_id', created_at DESC
        ) AS a
        WHERE r.id = a.request_id
          AND a.scope IN ('copy', 'design', 'both')
        """
    )


def downgrade() -> None:
    op.drop_column("approval_requests", "scope")
