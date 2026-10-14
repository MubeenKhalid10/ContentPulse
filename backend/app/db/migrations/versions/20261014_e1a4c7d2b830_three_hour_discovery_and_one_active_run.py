"""every-3-hours trend frequency (new default) and one active discovery run per organization

Revision ID: e1a4c7d2b830
Revises: b7d3e5a1c824
Create Date: 2026-10-14 10:00:00.000000

Existing organizations keep their stored trend_frequency: only the column
default (used for new rows) changes. The partial unique index makes "one
queued/running discovery run per organization" a database guarantee, so
concurrent manual and scheduled triggers can't both start one.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1a4c7d2b830"
down_revision: str | None = "b7d3e5a1c824"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_organization_settings_trend_frequency"
OLD = ("manual", "hourly", "every_6_hours", "daily")
NEW = ("manual", "hourly", "every_3_hours", "every_6_hours", "daily")
INDEX = "uq_trend_discovery_runs_one_active"


def _check(values: tuple[str, ...]) -> str:
    return "trend_frequency IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "organization_settings", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "organization_settings", _check(NEW))
    op.alter_column("organization_settings", "trend_frequency", server_default="every_3_hours")

    # An older duplicate active run can only be a leftover of a race or a
    # restart (the app keeps one per organization); close it the way the
    # app's stale-run recovery would, so the unique index can be built.
    op.execute(
        """
        UPDATE trend_discovery_runs AS r
        SET status = 'failed',
            error = 'Interrupted: superseded by a newer run.',
            finished_at = now()
        WHERE r.status IN ('queued', 'running')
          AND EXISTS (
            SELECT 1 FROM trend_discovery_runs AS newer
            WHERE newer.organization_id = r.organization_id
              AND newer.status IN ('queued', 'running')
              AND (newer.created_at, newer.id) > (r.created_at, r.id)
          )
        """
    )
    op.create_index(
        INDEX,
        "trend_discovery_runs",
        ["organization_id"],
        unique=True,
        postgresql_where="status IN ('queued', 'running')",
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="trend_discovery_runs")
    op.alter_column("organization_settings", "trend_frequency", server_default="daily")
    # The previous schema has no 3-hour option: the nearest one that collects
    # no more often than chosen is every 6 hours.
    op.execute(
        "UPDATE organization_settings SET trend_frequency = 'every_6_hours' "
        "WHERE trend_frequency = 'every_3_hours'"
    )
    op.drop_constraint(op.f(CONSTRAINT), "organization_settings", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "organization_settings", _check(OLD))
