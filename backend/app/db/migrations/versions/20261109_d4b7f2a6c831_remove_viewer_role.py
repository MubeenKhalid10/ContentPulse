"""remove the viewer role: only admin and creator remain

Revision ID: d4b7f2a6c831
Revises: a1c8e5d27b90

Existing viewers are disabled, not promoted: turning a read-only person into a
creator would silently give them write access. An admin can re-enable them and
pick a role. Their rows are kept.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4b7f2a6c831"
down_revision: str | None = "a1c8e5d27b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_organization_members_member_role"


def upgrade() -> None:
    op.execute(f"ALTER TABLE organization_members DROP CONSTRAINT {CONSTRAINT}")
    op.execute(
        "UPDATE organization_members SET role = 'creator', status = 'disabled' "
        "WHERE role = 'viewer'"
    )
    op.execute(
        f"ALTER TABLE organization_members ADD CONSTRAINT {CONSTRAINT} "
        "CHECK (role IN ('admin', 'creator'))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE organization_members DROP CONSTRAINT {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE organization_members ADD CONSTRAINT {CONSTRAINT} "
        "CHECK (role IN ('admin', 'creator', 'viewer'))"
    )
