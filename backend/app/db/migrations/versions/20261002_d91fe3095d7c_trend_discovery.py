"""trend discovery

Revision ID: d91fe3095d7c
Revises: 10724db9ceca
Create Date: 2026-10-02 14:34:07.122153

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d91fe3095d7c"
down_revision: str | None = "10724db9ceca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trend_discovery_runs",
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="discovery_run_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column(
            "trigger",
            sa.Enum(
                "manual",
                "scheduled",
                name="run_trigger",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "locations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("items_collected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trends_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trends_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mentions_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_trend_discovery_runs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_trend_discovery_runs_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_discovery_runs")),
    )
    op.create_index(
        "ix_trend_discovery_runs_org_created",
        "trend_discovery_runs",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_discovery_runs_organization_id"),
        "trend_discovery_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_discovery_runs_status"), "trend_discovery_runs", ["status"], unique=False
    )
    op.add_column(
        "organization_settings",
        sa.Column(
            "subreddits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "organization_settings",
        sa.Column(
            "rss_feeds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "trend_mentions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "trend_mentions", sa.Column("engagement_label", sa.String(length=120), nullable=True)
    )
    op.create_index(
        "ix_trends_org_last_seen", "trends", ["organization_id", "last_seen_at"], unique=False
    )

    # Existing organizations start with the free, keyless sources enabled.
    op.execute(
        """
        UPDATE organization_settings
        SET enabled_sources =
            '["google_trends", "google_news", "hacker_news", "reddit", "rss"]'::jsonb
        WHERE enabled_sources = '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.drop_index("ix_trends_org_last_seen", table_name="trends")
    op.drop_column("trend_mentions", "engagement_label")
    op.drop_column("trend_mentions", "last_seen_at")
    op.drop_column("organization_settings", "rss_feeds")
    op.drop_column("organization_settings", "subreddits")
    op.drop_index(op.f("ix_trend_discovery_runs_status"), table_name="trend_discovery_runs")
    op.drop_index(
        op.f("ix_trend_discovery_runs_organization_id"), table_name="trend_discovery_runs"
    )
    op.drop_index("ix_trend_discovery_runs_org_created", table_name="trend_discovery_runs")
    op.drop_table("trend_discovery_runs")
