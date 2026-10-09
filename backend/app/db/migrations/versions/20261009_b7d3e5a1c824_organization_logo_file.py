"""organization logo file: an uploaded logo, preferred over logo_url

Revision ID: b7d3e5a1c824
Revises: 9c4e1b7a2d60
Create Date: 2026-10-09 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3e5a1c824"
down_revision: str | None = "9c4e1b7a2d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("logo_storage_key", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "logo_storage_key")
