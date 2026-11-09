"""users.email_verified_at for local sign-in email confirmation

Revision ID: e5c8a3b7d192
Revises: d4b7f2a6c831
Create Date: 2026-11-10 10:00:00.000000

Existing accounts that can sign in (a password or an external identity) are
marked verified, so turning verification on never locks anyone out. Invitation
placeholders (no password yet) stay unverified until the invitation is accepted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5c8a3b7d192"
down_revision: str | None = "d4b7f2a6c831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE users SET email_verified_at = now() "
        "WHERE password_hash IS NOT NULL OR external_auth_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
