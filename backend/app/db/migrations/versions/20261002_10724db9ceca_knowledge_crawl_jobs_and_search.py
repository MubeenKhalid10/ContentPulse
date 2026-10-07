"""knowledge crawl jobs and search

Revision ID: 10724db9ceca
Revises: 08a75e6ffdda
Create Date: 2026-10-02 13:26:35.918448

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "10724db9ceca"
down_revision: str | None = "08a75e6ffdda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_crawl_jobs",
        sa.Column(
            "kind",
            sa.Enum(
                "crawl",
                "reindex",
                name="knowledge_job_kind",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                name="knowledge_job_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("root_url", sa.String(length=2048), nullable=True),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("pages_discovered", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_crawled", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_indexed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
            name=op.f("fk_knowledge_crawl_jobs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_knowledge_crawl_jobs_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_crawl_jobs")),
    )
    op.create_index(
        "ix_knowledge_crawl_jobs_org_created",
        "knowledge_crawl_jobs",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_crawl_jobs_organization_id"),
        "knowledge_crawl_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_crawl_jobs_status"), "knowledge_crawl_jobs", ["status"], unique=False
    )
    op.add_column(
        "knowledge_chunks", sa.Column("embedding_model", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
                "setweight(to_tsvector('english', content), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("knowledge_documents", sa.Column("last_crawl_job_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_knowledge_documents_last_crawl_job_id_knowledge_crawl_jobs"),
        "knowledge_documents",
        "knowledge_crawl_jobs",
        ["last_crawl_job_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_knowledge_documents_last_crawl_job_id_knowledge_crawl_jobs"),
        "knowledge_documents",
        type_="foreignkey",
    )
    op.drop_column("knowledge_documents", "last_crawl_job_id")
    op.drop_column("knowledge_documents", "word_count")
    op.drop_column("knowledge_documents", "excluded")
    op.drop_index(
        "ix_knowledge_chunks_search_vector", table_name="knowledge_chunks", postgresql_using="gin"
    )
    op.drop_column("knowledge_chunks", "search_vector")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_index(op.f("ix_knowledge_crawl_jobs_status"), table_name="knowledge_crawl_jobs")
    op.drop_index(
        op.f("ix_knowledge_crawl_jobs_organization_id"), table_name="knowledge_crawl_jobs"
    )
    op.drop_index("ix_knowledge_crawl_jobs_org_created", table_name="knowledge_crawl_jobs")
    op.drop_table("knowledge_crawl_jobs")
