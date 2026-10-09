"""Startup must create or adopt the schema on either dialect.

Pointing DATABASE_URL at an empty database and starting the app is the documented
way to run from source, so these cover the three states a database can be in.
The third one matters most: a database created before Alembic existed has our
tables but no ``alembic_version``, and replaying the baseline over it would fail
on tables that already exist.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.engine import _upgrade_or_adopt
from app.models.work import Work


async def _apply(db_path) -> None:
    """Run the startup schema step against a file database."""
    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with eng.begin() as conn:
            await conn.run_sync(_upgrade_or_adopt)
    finally:
        await eng.dispose()


def _tables(db_path) -> set[str]:
    with sqlite3.connect(db_path) as db:
        return {
            r[0] for r in db.execute("select name from sqlite_master where type='table'")
        }


def _version(db_path) -> str | None:
    with sqlite3.connect(db_path) as db:
        try:
            return db.execute("select version_num from alembic_version").fetchone()[0]
        except sqlite3.OperationalError:
            return None


async def test_empty_database_gets_the_whole_schema(tmp_path):
    db_path = tmp_path / "fresh.db"
    await _apply(db_path)

    tables = _tables(db_path)
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables
    assert _version(db_path) is not None


async def test_running_twice_is_a_no_op(tmp_path):
    """Startup runs this every time, so it has to be idempotent."""
    db_path = tmp_path / "twice.db"
    await _apply(db_path)
    first = _version(db_path)
    await _apply(db_path)
    assert _version(db_path) == first
    assert set(Base.metadata.tables) <= _tables(db_path)


async def test_a_pre_alembic_database_is_stamped_not_recreated(tmp_path):
    """The upgrade path would fail with "table already exists" here."""
    db_path = tmp_path / "legacy.db"

    # Build the schema the old way, without any Alembic bookkeeping, and put a
    # row in it so adoption can be shown to be non-destructive.
    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(eng, expire_on_commit=False)() as session:
        session.add(Work(id=uuid.uuid4(), title="Kept", author="A"))
        await session.commit()
    await eng.dispose()
    assert _version(db_path) is None

    await _apply(db_path)

    assert _version(db_path) is not None, "should have been stamped"
    with sqlite3.connect(db_path) as db:
        rows = db.execute("select title from works").fetchall()
    assert rows == [("Kept",)], "existing content must survive adoption"


async def test_an_unrelated_database_is_not_stamped(tmp_path):
    """Only our own tables count as evidence of a pre-Alembic database.

    A database holding someone else's tables should get the schema created, not
    be stamped as though it were already migrated.
    """
    db_path = tmp_path / "foreign.db"
    with sqlite3.connect(db_path) as db:
        db.execute("create table unrelated_thing (id integer primary key)")

    await _apply(db_path)

    tables = _tables(db_path)
    assert "unrelated_thing" in tables
    assert set(Base.metadata.tables) <= tables, "our tables should have been created"


async def test_schema_matches_the_models_after_bootstrap(tmp_path):
    """Whatever route the schema took, it must match what the ORM expects."""
    db_path = tmp_path / "match.db"
    await _apply(db_path)

    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with eng.connect() as conn:
            found = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            columns = await conn.run_sync(
                lambda c: {t: {col["name"] for col in inspect(c).get_columns(t)} for t in found}
            )
    finally:
        await eng.dispose()

    missing_tables = set(Base.metadata.tables) - found
    assert missing_tables == set()

    missing_columns = {}
    for name, table in Base.metadata.tables.items():
        expected = {c.name for c in table.columns}
        gap = expected - columns.get(name, set())
        if gap:
            missing_columns[name] = sorted(gap)
    assert missing_columns == {}, f"columns the ORM expects but the schema lacks: {missing_columns}"


@pytest.mark.parametrize(
    ("exc_name", "message", "expect"),
    [
        ("InvalidCatalogNameError", 'database "typecast" does not exist', "createdb"),
        ("InvalidPasswordError", "password authentication failed", "credentials"),
        ("OSError", "Connect call failed ('10.0.0.1', 5432)", "Could not reach"),
    ],
)
def test_connection_failures_explain_themselves(exc_name, message, expect, monkeypatch):
    """A first-run mistake should say what to do, not just surface the driver."""
    from app.db import engine as engine_module

    monkeypatch.setattr(
        type(engine_module.settings), "is_postgres", property(lambda self: True)
    )
    exc = type(exc_name, (Exception,), {})(message)
    assert expect in engine_module._connection_help(exc)


async def test_startup_migration_leaves_app_logging_alone(tmp_path):
    """alembic.ini's fileConfig disables every existing logger by default.

    Running migrations in-process at startup did exactly that, so request logs
    and unhandled-exception tracebacks vanished after the first startup. Found
    when a 500 on the cloud deployment left nothing in the container log.
    """
    import logging

    sentinel = logging.getLogger("typecast.http")
    handlers_before = list(logging.getLogger().handlers)

    await _apply(tmp_path / "logging.db")

    assert sentinel.disabled is False
    assert logging.getLogger("app.services.backup").disabled is False
    assert logging.getLogger().handlers == handlers_before


async def test_a_failed_migration_on_sqlite_leaves_no_partial_schema(tmp_path):
    """DDL must roll back with the rest of a failed migration.

    On the application engine an ALTER TABLE autocommits, because the sqlite3
    driver does not open a transaction for DDL. A migration that died after
    adding a column left the column behind with the version unchanged, so every
    later startup failed on "duplicate column name". This happened to a real
    development database.
    """
    from sqlalchemy import text

    from app.db.engine import make_migration_engine

    url = f"sqlite+aiosqlite:///{tmp_path / 'ddl.db'}"
    eng = make_migration_engine(url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="halfway"):
        async with eng.begin() as conn:
            await conn.execute(text("ALTER TABLE t ADD COLUMN added TEXT"))
            await conn.execute(text("CREATE INDEX ix_added ON t (added)"))
            raise RuntimeError("migration failed halfway")

    async with eng.connect() as conn:
        columns = [r[1] for r in (await conn.execute(text("PRAGMA table_info(t)"))).all()]
        indexes = [r[1] for r in (await conn.execute(text("PRAGMA index_list(t)"))).all()]
    await eng.dispose()
    assert columns == ["id"], f"partial DDL survived: {columns}"
    assert indexes == []


async def test_the_codex_owner_migration_backfills_without_losing_rows(tmp_path):
    """Attaches existing entries to their works' or series' owner.

    Also guards against the batch-mode trap: rebuilding codex_entries to add a
    foreign key on SQLite would cascade-delete every association and image.
    """
    import sqlite3

    db_path = tmp_path / "owners.db"
    from alembic.config import Config

    from alembic import command
    from app.db.engine import ALEMBIC_INI, BACKEND_DIR, make_migration_engine

    eng = make_migration_engine(f"sqlite+aiosqlite:///{db_path}")

    def upgrade(conn, target):
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, target)

    async with eng.begin() as conn:
        await conn.run_sync(upgrade, "b1199ab62ff7")

    def insert(db, table, **values):
        """Insert a row, filling any other NOT NULL column with a blank."""
        for _cid, name, col_type, notnull, _default, pk in db.execute(
            f"pragma table_info({table})"
        ):
            if name in values or not notnull or pk:
                continue
            kind = col_type.upper()
            numeric = any(k in kind for k in ("INT", "BOOL", "FLOAT"))
            values[name] = 0 if numeric else ""
        values.setdefault("id", uuid.uuid4().hex)
        db.execute(
            f"insert into {table} ({','.join(values)}) values ({','.join('?' * len(values))})",
            list(values.values()),
        )
        return values["id"]

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        owner = insert(db, "users", email="o@x", username="o", display_name="O",
                       hashed_password="h", is_active=1)
        work = insert(db, "works", title="W", author="A", user_id=owner, status="DRAFT")
        series = insert(db, "series", title="S", user_id=owner)
        e_work, e_series, e_none = (
            insert(db, "codex_entries", entry_type="CHARACTER", name=n)
            for n in ("in-work", "in-series", "unattached")
        )
        insert(db, "codex_associations", codex_entry_id=e_work, target_type="work",
               target_id=work)
        insert(db, "codex_associations", codex_entry_id=e_series, target_type="series",
               target_id=series)
        insert(db, "codex_images", codex_entry_id=e_work, filename="a.png",
               original_name="a.png", mime_type="image/png", size_bytes=1)

    async with eng.begin() as conn:
        await conn.run_sync(upgrade, "head")
    await eng.dispose()

    with sqlite3.connect(db_path) as db:
        owners = dict(db.execute("select id, user_id from codex_entries"))
        assert owners[e_work] == owner
        assert owners[e_series] == owner
        assert owners[e_none] is None
        assert db.execute("select count(*) from codex_associations").fetchone()[0] == 2
        assert db.execute("select count(*) from codex_images").fetchone()[0] == 1
        fk = db.execute(
            "select \"table\", on_delete from pragma_foreign_key_list('codex_entries')"
        ).fetchall()
        assert ("users", "CASCADE") in fk, "Alembic silently drops this on SQLite"
