"""sans-serif generic family

The font picker saved its sans-serif choices as ``Arial, 'sans serif'``. The
quoted ``'sans serif'`` is a family name that no font has, not the CSS generic
``sans-serif``, so a browser without the first-choice font fell back to its
default serif. Export was unaffected only because fontconfig aliases the name.

Rewrites the saved values to the generic. Data only, no schema change.

Revision ID: e7b3f19a4c2d
Revises: d4e8a1c2f6b0
Create Date: 2026-11-10

"""
from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3f19a4c2d"
down_revision: str | None = "d4e8a1c2f6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

OLD = "'sans serif'"
NEW = "sans-serif"
PROFILE_COLUMNS = ("font_family", "chapter_font_family", "header_font_family")


def _rewrite(old: str, new: str) -> None:
    bind = op.get_bind()
    params = {"old": old, "new": new, "pattern": f"%{old}%"}
    for column in PROFILE_COLUMNS:
        result = bind.execute(
            sa.text(
                f"UPDATE profiles SET {column} = REPLACE({column}, :old, :new) "
                f"WHERE {column} LIKE :pattern"
            ),
            params,
        )
        log.info("profiles.%s: rewrote %s row(s) from %s to %s", column, result.rowcount, old, new)

    # The title page config is JSON: TEXT on SQLite, json on Postgres. JSON leaves
    # single quotes unescaped, so a text replace is exact.
    if bind.dialect.name == "postgresql":
        sql = (
            "UPDATE works SET title_page_config = "
            "REPLACE(title_page_config::text, :old, :new)::json "
            "WHERE title_page_config::text LIKE :pattern"
        )
    else:
        sql = (
            "UPDATE works SET title_page_config = REPLACE(title_page_config, :old, :new) "
            "WHERE title_page_config LIKE :pattern"
        )
    result = bind.execute(sa.text(sql), params)
    log.info("works.title_page_config: rewrote %s row(s) from %s to %s", result.rowcount, old, new)


def upgrade() -> None:
    _rewrite(OLD, NEW)


def downgrade() -> None:
    # Not an exact inverse: a value saved as a bare sans-serif before this
    # migration would also be rewritten. Harmless, since the old form renders
    # the same in export and only worse in the browser.
    _rewrite(NEW, OLD)
