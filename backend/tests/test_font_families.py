"""The picker's sans-serif fonts must name the CSS generic, not a family called 'sans serif'.

``Arial, 'sans serif'`` reads, to a browser, as "Arial, else a font named
sans serif", which no system has, so a reader without Arial got its default
serif. Export hid it, since fontconfig aliases the name. Covers the picker, the
migration that rewrites saved values, and archives taken before it.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path

from app.services.portable import LoadSummary, decode_rows

PICKER = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "FontSelect.tsx"
MIGRATION = "e7b3f19a4c2d"


def test_the_picker_never_quotes_a_generic_family():
    values = re.findall(r'value: "([^"]+)"', PICKER.read_text())
    assert len(values) >= 10, "the picker's font list moved; update this test"
    quoted = [v for v in values if re.search(r"['\"](serif|sans[ -]serif|monospace)['\"]", v)]
    assert quoted == [], f"a quoted generic is a family name no font has: {quoted}"
    assert not any("sans serif" in v for v in values)


def _insert(db, table, **values):
    """Insert a row, filling any other NOT NULL column with a blank."""
    for _cid, name, col_type, notnull, _default, pk in db.execute(f"pragma table_info({table})"):
        if name in values or not notnull or pk:
            continue
        kind = col_type.upper()
        values[name] = 0 if any(k in kind for k in ("INT", "BOOL", "FLOAT")) else ""
    values.setdefault("id", uuid.uuid4().hex)
    db.execute(
        f"insert into {table} ({','.join(values)}) values ({','.join('?' * len(values))})",
        list(values.values()),
    )
    return values["id"]


async def test_the_migration_rewrites_saved_font_families(tmp_path):
    from alembic.config import Config

    from alembic import command
    from app.db.engine import ALEMBIC_INI, BACKEND_DIR, make_migration_engine

    db_path = tmp_path / "fonts.db"
    eng = make_migration_engine(f"sqlite+aiosqlite:///{db_path}")

    def upgrade(conn, target):
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, target)

    async with eng.begin() as conn:
        await conn.run_sync(upgrade, f"{MIGRATION}-1")

    config = {"title_font_family": "Verdana, 'sans serif'", "author_font_family": "Georgia, serif"}
    with sqlite3.connect(db_path) as db:
        owner = _insert(db, "users", email="o@x", username="o", display_name="O",
                        hashed_password="h", is_active=1)
        sans = _insert(db, "profiles", name="Sans", format="PDF",
                       font_family="Helvetica, 'sans serif'",
                       chapter_font_family="Arial, 'sans serif'", header_font_family=None)
        serif = _insert(db, "profiles", name="Serif", format="PDF", font_family="Georgia, serif")
        work = _insert(db, "works", title="W", author="A", user_id=owner, status="DRAFT",
                       title_page_config=json.dumps(config))

    async with eng.begin() as conn:
        await conn.run_sync(upgrade, "head")
    await eng.dispose()

    with sqlite3.connect(db_path) as db:
        rows = {r[0]: r[1:] for r in db.execute(
            "select id, font_family, chapter_font_family, header_font_family from profiles")}
        assert rows[sans] == ("Helvetica, sans-serif", "Arial, sans-serif", None)
        assert rows[serif] == ("Georgia, serif", None, None)
        stored = json.loads(db.execute(
            "select title_page_config from works where id = ?", (work,)).fetchone()[0])
        assert stored == {"title_font_family": "Verdana, sans-serif",
                          "author_font_family": "Georgia, serif"}


def test_an_archive_from_before_the_migration_loads_the_generic():
    """Without this, importing an older backup would put the old value straight back."""
    rows = {
        "profiles": [{
            "id": "0123456789abcdef0123456789abcdef", "name": "Sans", "format": "PDF",
            "is_builtin": 0, "font_family": "Arial, 'sans serif'",
            "chapter_font_family": "Verdana, 'sans serif'", "header_font_family": None,
        }],
        "works": [{
            "id": "fedcba9876543210fedcba9876543210", "title": "W", "status": "DRAFT",
            "title_page_config": {"subtitle_font_family": "Helvetica, 'sans serif'"},
        }],
    }
    decoded = decode_rows(rows, LoadSummary(mode="import"))
    profile = decoded["profiles"][0]
    assert profile["font_family"] == "Arial, sans-serif"
    assert profile["chapter_font_family"] == "Verdana, sans-serif"
    assert profile["header_font_family"] is None
    config = decoded["works"][0]["title_page_config"]
    assert config["subtitle_font_family"] == "Helvetica, sans-serif"
