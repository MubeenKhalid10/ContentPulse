"""simplify roles and workflow: one creator role, no review step, approve = final

- content_manager and designer merge into "creator".
- Posts "In review" (content_review, a step with no reviewer) go back to draft.
- Approved posts become final: approving now marks a post ready to publish.

Revision ID: 5d8a2f4c7e91
Revises: 7b2e5c1d9a30
Create Date: 2026-10-06 19:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "5d8a2f4c7e91"
down_revision: str | None = "7b2e5c1d9a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_organization_members_member_role"


def upgrade() -> None:
    op.execute(f"ALTER TABLE organization_members DROP CONSTRAINT {CONSTRAINT}")
    op.execute(
        "UPDATE organization_members SET role = 'creator' "
        "WHERE role IN ('content_manager', 'designer')"
    )
    op.execute(
        f"ALTER TABLE organization_members ADD CONSTRAINT {CONSTRAINT} "
        "CHECK (role IN ('admin', 'creator', 'viewer'))"
    )
    op.execute("UPDATE posts SET status = 'draft' WHERE status = 'content_review'")
    op.execute("UPDATE posts SET status = 'final' WHERE status = 'approved'")


def downgrade() -> None:
    # Creators become content managers (the broader of the two old roles).
    op.execute(f"ALTER TABLE organization_members DROP CONSTRAINT {CONSTRAINT}")
    op.execute("UPDATE organization_members SET role = 'content_manager' WHERE role = 'creator'")
    op.execute(
        f"ALTER TABLE organization_members ADD CONSTRAINT {CONSTRAINT} "
        "CHECK (role IN ('admin', 'content_manager', 'designer', 'viewer'))"
    )
