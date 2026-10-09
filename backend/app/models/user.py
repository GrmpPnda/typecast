from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Identity at the single sign-on provider, set on first SSO sign-in. For
    # Microsoft Entra ID this is the object ID (oid), which unlike the email or
    # UPN never changes. NULL for password accounts and for SSO accounts an
    # administrator has created that have not signed in yet.
    # A unique *index*, not a constraint: SQLite cannot add a UNIQUE column to an
    # existing table, and the migration has to work on both databases.
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None, unique=True, index=True
    )
