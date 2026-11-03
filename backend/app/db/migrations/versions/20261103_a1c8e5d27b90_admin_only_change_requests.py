"""admin-only change requests: retire creator requests, add notifications

Revision ID: a1c8e5d27b90
Revises: e9a3c6f1d284
Create Date: 2026-11-03 12:00:00.000000

Only an admin can request changes now. Creators' requests that were still waiting
are closed (kept as history, never deleted). Adds `notifications`, a new empty
table with row level security on and client privileges revoked, like the other
backend-only tables.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c8e5d27b90"
down_revision: str | None = "e9a3c6f1d284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE post_change_requests SET status = 'closed', decided_at = now() "
        "WHERE status = 'pending'"
    )
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("scope", sa.String(20)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("link", sa.String(300), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_post_id", "notifications", ["post_id"])
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "read_at"])
    op.create_index(
        "uq_notifications_user_dedupe", "notifications", ["user_id", "dedupe_key"], unique=True
    )
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON notifications FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON notifications FROM authenticated;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("notifications")
