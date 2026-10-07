from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, str_enum
from app.models.enums import AuthProvider


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[AuthProvider] = mapped_column(
        str_enum(AuthProvider, "auth_provider"),
        default=AuthProvider.LOCAL,
        server_default=AuthProvider.LOCAL.value,
        nullable=False,
    )
    # Subject id from an external identity provider (e.g. Supabase `sub`).
    external_auth_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
