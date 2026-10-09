"""user external id

Links accounts to a single sign-on identity (proxy auth mode). Nullable, since
password accounts never have one and SSO accounts get it on first sign-in.

Revision ID: ac5789a097c3
Revises: b943e3ac703f
Create Date: 2026-10-09

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ac5789a097c3"
down_revision: str | None = "b943e3ac703f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain column plus a unique index. SQLite refuses ADD COLUMN ... UNIQUE, and
    # a unique index treats NULLs as distinct on both databases, so every
    # password account can keep a NULL here.
    op.add_column("users", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.create_index("ix_users_external_id", "users", ["external_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_column("users", "external_id")
