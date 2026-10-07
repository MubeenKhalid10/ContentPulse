"""map legacy trend source keys

Revision ID: b40db2a2a624
Revises: d91fe3095d7c
Create Date: 2026-10-02 14:57:14.744674

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b40db2a2a624"
down_revision: str | None = "d91fe3095d7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


KNOWN = (
    "google_trends",
    "google_news",
    "hacker_news",
    "reddit",
    "rss",
    "newsapi",
    "gnews",
    "x",
    "instagram",
    "linkedin",
)


def upgrade() -> None:
    # Sprint 1 settings offered a generic "news" source; it is now Google News.
    # Unknown keys are dropped and duplicates removed, preserving order.
    op.execute(
        sa.text(
            """
            UPDATE organization_settings s
            SET enabled_sources = COALESCE(
                (
                    SELECT jsonb_agg(key ORDER BY first_pos)
                    FROM (
                        SELECT key, MIN(pos) AS first_pos
                        FROM (
                            SELECT
                                CASE WHEN value = 'news' THEN 'google_news' ELSE value END AS key,
                                pos
                            FROM jsonb_array_elements_text(s.enabled_sources)
                                WITH ORDINALITY AS e(value, pos)
                        ) mapped
                        WHERE key = ANY(:known)
                        GROUP BY key
                    ) deduped
                ),
                '[]'::jsonb
            )
            WHERE enabled_sources ?| ARRAY['news']
               OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(s.enabled_sources) v
                    WHERE v <> ALL(:known)
               )
            """
        ).bindparams(sa.bindparam("known", value=list(KNOWN), type_=sa.ARRAY(sa.Text)))
    )


def downgrade() -> None:
    # Data-only migration; the previous keys are not restored.
    pass
