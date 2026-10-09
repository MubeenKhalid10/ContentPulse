"""brand logo position: where the real logo goes on AI-generated images

Revision ID: 9c4e1b7a2d60
Revises: 5d8a2f4c7e91
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e1b7a2d60"
down_revision: str | None = "5d8a2f4c7e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSITIONS = (
    "top_left",
    "top_center",
    "top_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
    "none",
)


def upgrade() -> None:
    op.add_column(
        "brand_profiles",
        sa.Column(
            "logo_position",
            sa.String(20),
            nullable=False,
            server_default="bottom_right",
        ),
    )
    allowed = ", ".join(f"'{p}'" for p in POSITIONS)
    op.create_check_constraint(
        op.f("ck_brand_profiles_logo_position"),
        "brand_profiles",
        f"logo_position IN ({allowed})",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_brand_profiles_logo_position"), "brand_profiles", type_="check")
    op.drop_column("brand_profiles", "logo_position")
