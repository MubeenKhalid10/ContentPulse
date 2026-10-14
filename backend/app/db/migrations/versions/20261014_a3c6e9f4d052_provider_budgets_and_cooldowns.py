"""provider request budgets, cooldowns and the Instagram hashtag ledger

Revision ID: a3c6e9f4d052
Revises: f2b5d8e3c941
Create Date: 2026-10-14 14:00:00.000000

Additive: two new backend-only tables and three nullable/defaulted columns on
trend_sources. Budgets start in monitor-only mode (PROVIDER_BUDGET_MODE).

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c6e9f4d052"
down_revision: str | None = "f2b5d8e3c941"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trend_sources", sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("trend_sources", sa.Column("cooldown_reason", sa.String(200), nullable=True))
    op.add_column(
        "trend_sources",
        sa.Column("failure_streak", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "provider_usage",
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("reserved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("over_budget", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("source", "usage_date", "scope", name=op.f("pk_provider_usage")),
    )
    op.create_table(
        "instagram_hashtag_usage",
        sa.Column("account", sa.String(16), nullable=False),
        sa.Column("hashtag", sa.String(100), nullable=False),
        sa.Column(
            "first_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("account", "hashtag", name=op.f("pk_instagram_hashtag_usage")),
    )
    op.create_index(
        op.f("ix_instagram_hashtag_usage_last_used_at"),
        "instagram_hashtag_usage",
        ["last_used_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_instagram_hashtag_usage_last_used_at"), table_name="instagram_hashtag_usage"
    )
    op.drop_table("instagram_hashtag_usage")
    op.drop_table("provider_usage")
    op.drop_column("trend_sources", "failure_streak")
    op.drop_column("trend_sources", "cooldown_reason")
    op.drop_column("trend_sources", "cooldown_until")
