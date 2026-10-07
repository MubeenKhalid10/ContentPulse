import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrgScoped:
    """Every organization-owned table carries organization_id (spec §62)."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Store enums as VARCHAR + CHECK constraint (cheap to migrate, readable in SQL)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def jsonb_list(**kwargs) -> Mapped[list]:
    return mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list, nullable=False, **kwargs
    )


def jsonb_dict(**kwargs) -> Mapped[dict]:
    return mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), default=dict, nullable=False, **kwargs
    )


def fk_user(nullable: bool = True, **kwargs) -> Mapped[uuid.UUID | None]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=nullable,
        **kwargs,
    )
