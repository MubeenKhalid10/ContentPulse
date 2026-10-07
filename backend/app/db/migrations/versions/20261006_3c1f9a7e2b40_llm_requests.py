"""llm request log for the LLM gateway

Revision ID: 3c1f9a7e2b40
Revises: 14801f0e80bc
Create Date: 2026-10-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3c1f9a7e2b40"
down_revision: str | None = "14801f0e80bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_requests",
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("workflow", sa.String(length=60), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_kind", sa.String(length=40), nullable=True),
        sa.Column("error_detail", sa.String(length=300), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("queue_wait_ms", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_unavailable", sa.Boolean(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_requests_call_id"), "llm_requests", ["call_id"])
    op.create_index(op.f("ix_llm_requests_job_id"), "llm_requests", ["job_id"])
    op.create_index(
        "ix_llm_requests_org_created", "llm_requests", ["organization_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_llm_requests_org_created", table_name="llm_requests")
    op.drop_index(op.f("ix_llm_requests_job_id"), table_name="llm_requests")
    op.drop_index(op.f("ix_llm_requests_call_id"), table_name="llm_requests")
    op.drop_table("llm_requests")
