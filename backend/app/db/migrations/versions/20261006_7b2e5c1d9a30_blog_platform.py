"""blog platform and platform-specific strategy details

Revision ID: 7b2e5c1d9a30
Revises: 3c1f9a7e2b40
Create Date: 2026-10-06 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b2e5c1d9a30"
down_revision: str | None = "3c1f9a7e2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("content_strategies", "posts", "platform_rules")
OLD = ("linkedin", "x", "instagram", "facebook")
NEW = (*OLD, "blog")


def _check(values: tuple[str, ...]) -> str:
    return "platform IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _replace_checks(values: tuple[str, ...]) -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f"ck_{table}_platform"), table, type_="check")
        # Already-prefixed name: bypass the naming convention.
        op.create_check_constraint(op.f(f"ck_{table}_platform"), table, _check(values))


def upgrade() -> None:
    _replace_checks(NEW)
    op.add_column(
        "content_strategies",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("content_strategies", "details")
    for table in TABLES:
        op.execute(f"DELETE FROM {table} WHERE platform = 'blog'")
    _replace_checks(OLD)
