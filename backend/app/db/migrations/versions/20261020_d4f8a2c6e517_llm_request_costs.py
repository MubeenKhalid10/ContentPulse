"""llm_requests cost telemetry: cached input tokens, images, cost_usd

Revision ID: d4f8a2c6e517
Revises: c8e2f5a7b391
Create Date: 2026-10-20 12:00:00.000000

Nullable columns only, so the upgrade is a metadata change (no table rewrite)
and older rows simply have no cost.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f8a2c6e517"
down_revision: str | None = "c8e2f5a7b391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_requests", sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_requests", sa.Column("image_count", sa.Integer(), nullable=True))
    op.add_column("llm_requests", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_requests", "cost_usd")
    op.drop_column("llm_requests", "image_count")
    op.drop_column("llm_requests", "cached_input_tokens")
