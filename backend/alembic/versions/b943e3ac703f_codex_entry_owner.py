"""codex entry owner

Gives codex entries their own owning account. Ownership used to be implied by
associations to works and series, but an entry created from the global codex
page has none, so it could not be attributed to anyone.

Revision ID: b943e3ac703f
Revises: b1199ab62ff7
Create Date: 2026-10-09 10:55:43.772736

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b943e3ac703f"
down_revision: str | None = "b1199ab62ff7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The foreign key is declared on the column, not added afterwards. SQLite
    # cannot add a constraint to an existing table, and Alembic's batch mode
    # works around that by copying the table and dropping the original, which
    # with foreign keys enabled cascade-deletes every codex association and
    # codex image. A nullable column with an inline REFERENCES is accepted by
    # SQLite's ADD COLUMN and by Postgres alike.
    if op.get_bind().dialect.name == "sqlite":
        # Alembic drops an inline ForeignKey from ADD COLUMN on SQLite without a
        # warning, so write it out. CHAR(32) is how sa.Uuid renders there.
        op.execute(
            "ALTER TABLE codex_entries ADD COLUMN user_id CHAR(32) "
            "REFERENCES users (id) ON DELETE CASCADE"
        )
    else:
        op.add_column(
            "codex_entries",
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
    op.create_index("ix_codex_entries_user_id", "codex_entries", ["user_id"], unique=False)

    # Attribute existing entries to the owner of a work they belong to, else of
    # a series. Correlated subqueries with LIMIT behave the same on both
    # databases. Entries with neither stay NULL; local mode assigns those to
    # the local user on startup.
    for target, table in (("work", "works"), ("series", "series")):
        op.execute(
            f"""
            UPDATE codex_entries SET user_id = (
                SELECT t.user_id FROM codex_associations a
                JOIN {table} t ON t.id = a.target_id
                WHERE a.codex_entry_id = codex_entries.id
                  AND a.target_type = '{target}'
                  AND t.user_id IS NOT NULL
                LIMIT 1
            )
            WHERE user_id IS NULL
            """
        )


def downgrade() -> None:
    op.drop_index("ix_codex_entries_user_id", table_name="codex_entries")
    op.drop_column("codex_entries", "user_id")
