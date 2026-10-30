"""post_change_requests: a creator asks an admin to reopen locked work

Revision ID: e9a3c6f1d284
Revises: c5f1a9d3e728
Create Date: 2026-10-30 12:00:00.000000

Creators can't reopen locked copy or designs themselves. They file a request
(what should change and why) and an admin accepts or declines it. Additive: a
new, empty table. Row level security is on, like every application table.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9a3c6f1d284"
down_revision: str | None = "c5f1a9d3e728"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_change_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_post_change_requests_organization_id", "post_change_requests", ["organization_id"]
    )
    op.create_index("ix_post_change_requests_post_id", "post_change_requests", ["post_id"])
    op.create_index(
        "uq_post_change_requests_one_pending",
        "post_change_requests",
        ["post_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute("ALTER TABLE post_change_requests ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("post_change_requests")
