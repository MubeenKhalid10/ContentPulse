"""initial core schema

Revision ID: 08a75e6ffdda
Revises:
Create Date: 2026-10-02 12:36:24.853951

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "08a75e6ffdda"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_table(
        "prompt_templates",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_templates")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_prompt_templates_name")),
    )
    op.create_table(
        "trend_sources",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "health",
            sa.Enum(
                "unknown",
                "healthy",
                "degraded",
                "rate_limited",
                "down",
                name="source_health",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "rate_limit",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_trend_sources_key")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "auth_provider",
            sa.Enum(
                "local",
                "supabase",
                name="auth_provider",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="local",
            nullable=False,
        ),
        sa.Column("external_auth_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_auth_id", name=op.f("uq_users_external_auth_id")),
    )
    op.create_table(
        "ai_generation_jobs",
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("prompt_template_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_ai_generation_jobs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"],
            ["prompt_templates.id"],
            name=op.f("fk_ai_generation_jobs_prompt_template_id_prompt_templates"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_generation_jobs")),
    )
    op.create_index(
        op.f("ix_ai_generation_jobs_entity_id"), "ai_generation_jobs", ["entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_generation_jobs_organization_id"),
        "ai_generation_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_generation_jobs_status"), "ai_generation_jobs", ["status"], unique=False
    )
    op.create_table(
        "audit_logs",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_logs_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False
    )
    op.create_index(
        "ix_audit_logs_org_created", "audit_logs", ["organization_id", "created_at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"], unique=False
    )
    op.create_table(
        "brand_profiles",
        sa.Column("brand_voice", sa.Text(), nullable=True),
        sa.Column("tone", sa.Text(), nullable=True),
        sa.Column("writing_style", sa.Text(), nullable=True),
        sa.Column(
            "preferred_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "forbidden_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_guidelines", sa.Text(), nullable=True),
        sa.Column("cta_guidelines", sa.Text(), nullable=True),
        sa.Column("hashtag_guidelines", sa.Text(), nullable=True),
        sa.Column(
            "brand_colors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("typography", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            name=op.f("fk_brand_profiles_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brand_profiles")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_brand_profiles_organization_id")),
    )
    op.create_index(
        op.f("ix_brand_profiles_organization_id"),
        "brand_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("document_type", sa.String(length=40), server_default="web_page", nullable=False),
        sa.Column(
            "crawl_status",
            sa.Enum(
                "pending",
                "crawling",
                "extracted",
                "embedded",
                "failed",
                name="crawl_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("crawl_error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            name=op.f("fk_knowledge_documents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "organization_id", "source_url", name=op.f("uq_knowledge_documents_organization_id")
        ),
    )
    op.create_index(
        op.f("ix_knowledge_documents_organization_id"),
        "knowledge_documents",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "organization_members",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "content_manager",
                "designer",
                "viewer",
                name="member_role",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "invited",
                "disabled",
                name="member_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_organization_members_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organization_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_members")),
        sa.UniqueConstraint(
            "invite_token_hash", name=op.f("uq_organization_members_invite_token_hash")
        ),
        sa.UniqueConstraint(
            "organization_id", "user_id", name=op.f("uq_organization_members_organization_id")
        ),
    )
    op.create_index(
        op.f("ix_organization_members_organization_id"),
        "organization_members",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_members_user_id"), "organization_members", ["user_id"], unique=False
    )
    op.create_table(
        "organization_services",
        sa.Column(
            "kind",
            sa.Enum(
                "service",
                "product",
                "expertise",
                name="offering_kind",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="service",
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            name=op.f("fk_organization_services_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_services")),
    )
    op.create_index(
        op.f("ix_organization_services_organization_id"),
        "organization_services",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "organization_settings",
        sa.Column("default_language", sa.String(length=16), server_default="en", nullable=False),
        sa.Column("default_timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column(
            "target_markets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column(
            "content_goals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "enabled_platforms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "enabled_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tracked_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "trend_frequency",
            sa.Enum(
                "manual",
                "hourly",
                "every_6_hours",
                "daily",
                name="trend_frequency",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="daily",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            name=op.f("fk_organization_settings_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_settings")),
        sa.UniqueConstraint(
            "organization_id", name=op.f("uq_organization_settings_organization_id")
        ),
    )
    op.create_index(
        op.f("ix_organization_settings_organization_id"),
        "organization_settings",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "trends",
        sa.Column("canonical_key", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column(
            "locations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "analyzed",
                "shortlisted",
                "rejected",
                "archived",
                name="trend_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mention_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("opportunity_score", sa.Float(), nullable=True),
        sa.Column(
            "relevance_level",
            sa.Enum(
                "highly_relevant",
                "relevant",
                "weakly_relevant",
                "not_relevant",
                name="relevance_level",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("relevance_confidence", sa.Float(), nullable=True),
        sa.Column("relevance_overridden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "alignment",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            name=op.f("fk_trends_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trends")),
        sa.UniqueConstraint(
            "organization_id", "canonical_key", name=op.f("uq_trends_organization_id")
        ),
    )
    op.create_index(
        op.f("ix_trends_opportunity_score"), "trends", ["opportunity_score"], unique=False
    )
    op.create_index(op.f("ix_trends_organization_id"), "trends", ["organization_id"], unique=False)
    op.create_index(op.f("ix_trends_relevance_level"), "trends", ["relevance_level"], unique=False)
    op.create_index(op.f("ix_trends_status"), "trends", ["status"], unique=False)
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_knowledge_chunks_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name=op.f("uq_knowledge_chunks_document_id")
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks", ["document_id"], unique=False
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_knowledge_chunks_organization_id"),
        "knowledge_chunks",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "topic_candidates",
        sa.Column("trend_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "relevance_level",
            sa.Enum(
                "highly_relevant",
                "relevant",
                "weakly_relevant",
                "not_relevant",
                name="relevance_level",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("relevance_reason", sa.Text(), nullable=True),
        sa.Column(
            "matched_services",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "suggested_angles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column(
            "recommended_platforms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "reviewed",
                "shortlisted",
                "rejected",
                "archived",
                name="topic_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            name=op.f("fk_topic_candidates_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_topic_candidates_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trend_id"],
            ["trends.id"],
            name=op.f("fk_topic_candidates_trend_id_trends"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_candidates")),
    )
    op.create_index(
        op.f("ix_topic_candidates_organization_id"),
        "topic_candidates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_topic_candidates_status"), "topic_candidates", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_topic_candidates_trend_id"), "topic_candidates", ["trend_id"], unique=False
    )
    op.create_table(
        "trend_mentions",
        sa.Column("trend_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_item_id", sa.String(length=500), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=80), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("author", sa.String(length=300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engagement", sa.BigInteger(), nullable=True),
        sa.Column("growth_indicator", sa.Float(), nullable=True),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_trend_mentions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trend_id"],
            ["trends.id"],
            name=op.f("fk_trend_mentions_trend_id_trends"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_mentions")),
        sa.UniqueConstraint(
            "organization_id",
            "source",
            "source_item_id",
            name=op.f("uq_trend_mentions_organization_id"),
        ),
    )
    op.create_index(
        op.f("ix_trend_mentions_organization_id"),
        "trend_mentions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_mentions_trend_id"), "trend_mentions", ["trend_id"], unique=False
    )
    op.create_table(
        "content_strategies",
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column(
            "platform",
            sa.Enum(
                "linkedin",
                "x",
                "instagram",
                "facebook",
                name="platform",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("post_type", sa.String(length=60), nullable=False),
        sa.Column("content_angle", sa.Text(), nullable=True),
        sa.Column("objective", sa.String(length=120), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("hook_direction", sa.Text(), nullable=True),
        sa.Column("cta_direction", sa.Text(), nullable=True),
        sa.Column("tone", sa.String(length=120), nullable=True),
        sa.Column("recommended_format", sa.String(length=60), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "approved",
                "archived",
                name="strategy_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_content_strategies_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_content_strategies_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topic_candidates.id"],
            name=op.f("fk_content_strategies_topic_id_topic_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_strategies")),
    )
    op.create_index(
        op.f("ix_content_strategies_organization_id"),
        "content_strategies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_strategies_topic_id"), "content_strategies", ["topic_id"], unique=False
    )
    op.create_table(
        "posts",
        sa.Column("topic_id", sa.UUID(), nullable=True),
        sa.Column("content_strategy_id", sa.UUID(), nullable=True),
        sa.Column(
            "platform",
            sa.Enum(
                "linkedin",
                "x",
                "instagram",
                "facebook",
                name="platform",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "content_review",
                "design_pending",
                "design_in_progress",
                "design_uploaded",
                "pending_approval",
                "changes_requested",
                "approved",
                "final",
                "rejected",
                "archived",
                name="post_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_strategy_id"],
            ["content_strategies.id"],
            name=op.f("fk_posts_content_strategy_id_content_strategies"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_posts_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_posts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topic_candidates.id"],
            name=op.f("fk_posts_topic_id_topic_candidates"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
    )
    op.create_index(op.f("ix_posts_organization_id"), "posts", ["organization_id"], unique=False)
    op.create_index(op.f("ix_posts_status"), "posts", ["status"], unique=False)
    op.create_index(op.f("ix_posts_topic_id"), "posts", ["topic_id"], unique=False)
    op.create_table(
        "approval_requests",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("post_version", sa.Integer(), nullable=False),
        sa.Column("creative_version", sa.Integer(), nullable=True),
        sa.Column("submitted_by", sa.UUID(), nullable=True),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "changes_requested",
                "rejected",
                name="approval_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_approval_requests_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_approval_requests_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_approval_requests_reviewer_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name=op.f("fk_approval_requests_submitted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        op.f("ix_approval_requests_organization_id"),
        "approval_requests",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_post_id"), "approval_requests", ["post_id"], unique=False
    )
    op.create_index(
        op.f("ix_approval_requests_status"), "approval_requests", ["status"], unique=False
    )
    op.create_table(
        "design_briefs",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("format", sa.String(length=60), nullable=False),
        sa.Column("dimensions", sa.String(length=40), nullable=True),
        sa.Column("visual_concept", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("supporting_text", sa.Text(), nullable=True),
        sa.Column(
            "slide_structure",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "visual_elements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "brand_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("designer_notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "assigned",
                "in_progress",
                "submitted",
                "completed",
                "cancelled",
                name="design_brief_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            name=op.f("fk_design_briefs_assignee_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_design_briefs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_design_briefs_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_briefs")),
    )
    op.create_index(
        op.f("ix_design_briefs_assignee_id"), "design_briefs", ["assignee_id"], unique=False
    )
    op.create_index(
        op.f("ix_design_briefs_organization_id"), "design_briefs", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_design_briefs_post_id"), "design_briefs", ["post_id"], unique=False)
    op.create_index(op.f("ix_design_briefs_status"), "design_briefs", ["status"], unique=False)
    op.create_table(
        "post_versions",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column(
            "hashtags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "mentions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "ai",
                "manual",
                name="version_source",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("ai_generation_job_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_generation_job_id"],
            ["ai_generation_jobs.id"],
            name=op.f("fk_post_versions_ai_generation_job_id_ai_generation_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_post_versions_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_post_versions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_post_versions_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_versions")),
        sa.UniqueConstraint("post_id", "version_number", name=op.f("uq_post_versions_post_id")),
    )
    op.create_index(
        op.f("ix_post_versions_organization_id"), "post_versions", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_post_versions_post_id"), "post_versions", ["post_id"], unique=False)
    op.create_table(
        "approval_comments",
        sa.Column("approval_request_id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("post_version", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["approval_requests.id"],
            name=op.f("fk_approval_comments_approval_request_id_approval_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_approval_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_approval_comments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_approval_comments_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_comments")),
    )
    op.create_index(
        op.f("ix_approval_comments_approval_request_id"),
        "approval_comments",
        ["approval_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_comments_organization_id"),
        "approval_comments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_comments_post_id"), "approval_comments", ["post_id"], unique=False
    )
    op.create_table(
        "creative_assets",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("design_brief_id", sa.UUID(), nullable=True),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_url", sa.String(length=2048), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=2048), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["design_brief_id"],
            ["design_briefs.id"],
            name=op.f("fk_creative_assets_design_brief_id_design_briefs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_creative_assets_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_creative_assets_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_creative_assets_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_creative_assets")),
    )
    op.create_index(
        op.f("ix_creative_assets_organization_id"),
        "creative_assets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_creative_assets_post_id"), "creative_assets", ["post_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_creative_assets_post_id"), table_name="creative_assets")
    op.drop_index(op.f("ix_creative_assets_organization_id"), table_name="creative_assets")
    op.drop_table("creative_assets")
    op.drop_index(op.f("ix_approval_comments_post_id"), table_name="approval_comments")
    op.drop_index(op.f("ix_approval_comments_organization_id"), table_name="approval_comments")
    op.drop_index(op.f("ix_approval_comments_approval_request_id"), table_name="approval_comments")
    op.drop_table("approval_comments")
    op.drop_index(op.f("ix_post_versions_post_id"), table_name="post_versions")
    op.drop_index(op.f("ix_post_versions_organization_id"), table_name="post_versions")
    op.drop_table("post_versions")
    op.drop_index(op.f("ix_design_briefs_status"), table_name="design_briefs")
    op.drop_index(op.f("ix_design_briefs_post_id"), table_name="design_briefs")
    op.drop_index(op.f("ix_design_briefs_organization_id"), table_name="design_briefs")
    op.drop_index(op.f("ix_design_briefs_assignee_id"), table_name="design_briefs")
    op.drop_table("design_briefs")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_post_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_organization_id"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_posts_topic_id"), table_name="posts")
    op.drop_index(op.f("ix_posts_status"), table_name="posts")
    op.drop_index(op.f("ix_posts_organization_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_content_strategies_topic_id"), table_name="content_strategies")
    op.drop_index(op.f("ix_content_strategies_organization_id"), table_name="content_strategies")
    op.drop_table("content_strategies")
    op.drop_index(op.f("ix_trend_mentions_trend_id"), table_name="trend_mentions")
    op.drop_index(op.f("ix_trend_mentions_organization_id"), table_name="trend_mentions")
    op.drop_table("trend_mentions")
    op.drop_index(op.f("ix_topic_candidates_trend_id"), table_name="topic_candidates")
    op.drop_index(op.f("ix_topic_candidates_status"), table_name="topic_candidates")
    op.drop_index(op.f("ix_topic_candidates_organization_id"), table_name="topic_candidates")
    op.drop_table("topic_candidates")
    op.drop_index(op.f("ix_knowledge_chunks_organization_id"), table_name="knowledge_chunks")
    op.drop_index(
        "ix_knowledge_chunks_embedding_hnsw",
        table_name="knowledge_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(op.f("ix_trends_status"), table_name="trends")
    op.drop_index(op.f("ix_trends_relevance_level"), table_name="trends")
    op.drop_index(op.f("ix_trends_organization_id"), table_name="trends")
    op.drop_index(op.f("ix_trends_opportunity_score"), table_name="trends")
    op.drop_table("trends")
    op.drop_index(
        op.f("ix_organization_settings_organization_id"), table_name="organization_settings"
    )
    op.drop_table("organization_settings")
    op.drop_index(
        op.f("ix_organization_services_organization_id"), table_name="organization_services"
    )
    op.drop_table("organization_services")
    op.drop_index(op.f("ix_organization_members_user_id"), table_name="organization_members")
    op.drop_index(
        op.f("ix_organization_members_organization_id"), table_name="organization_members"
    )
    op.drop_table("organization_members")
    op.drop_index(op.f("ix_knowledge_documents_organization_id"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index(op.f("ix_brand_profiles_organization_id"), table_name="brand_profiles")
    op.drop_table("brand_profiles")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_ai_generation_jobs_status"), table_name="ai_generation_jobs")
    op.drop_index(op.f("ix_ai_generation_jobs_organization_id"), table_name="ai_generation_jobs")
    op.drop_index(op.f("ix_ai_generation_jobs_entity_id"), table_name="ai_generation_jobs")
    op.drop_table("ai_generation_jobs")
    op.drop_table("users")
    op.drop_table("trend_sources")
    op.drop_table("prompt_templates")
    op.drop_table("organizations")
