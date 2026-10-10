"""user auth provider

Each account signs in exactly one way: ``password``, ``microsoft``, ``google``,
or ``external`` (an authenticating proxy, TYPECAST_AUTH_MODE=proxy). NULL is an
account an administrator created for single sign-on that nobody has signed in
to yet; its first sign-in decides.

Existing rows: an account already linked to an identity came through the proxy,
so it is ``external``; every other account has a password.

Revision ID: d4e8a1c2f6b0
Revises: ac5789a097c3
Create Date: 2026-10-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8a1c2f6b0"
down_revision: str | None = "ac5789a097c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A plain nullable column; no batch mode, since other tables reference users.
    op.add_column("users", sa.Column("auth_provider", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE users SET auth_provider = CASE "
        "WHEN external_id IS NOT NULL THEN 'external' ELSE 'password' END"
    )


def downgrade() -> None:
    op.drop_column("users", "auth_provider")
