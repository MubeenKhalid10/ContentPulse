"""shared provider-response cache (backend-only)

Revision ID: f2b5d8e3c941
Revises: e1a4c7d2b830
Create Date: 2026-10-14 12:00:00.000000

Additive: a new table nothing else depends on. Used only when
PROVIDER_CACHE_BACKEND=postgres and a provider is listed in
PROVIDER_CACHE_PERSIST_SOURCES.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2b5d8e3c941"
down_revision: str | None = "e1a4c7d2b830"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_cache",
        sa.Column("key", sa.CHAR(64), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("content_type", sa.String(200), nullable=True),
        sa.Column("body", sa.LargeBinary(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_provider_cache")),
    )
    op.create_index("ix_provider_cache_expires_at", "provider_cache", ["expires_at"])
    op.create_index(op.f("ix_provider_cache_source"), "provider_cache", ["source"])


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_cache_source"), table_name="provider_cache")
    op.drop_index("ix_provider_cache_expires_at", table_name="provider_cache")
    op.drop_table("provider_cache")
