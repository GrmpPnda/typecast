"""Engine, session factory, and startup schema work.

Alembic owns the schema on both SQLite and Postgres, and startup brings the
database up to date so that pointing ``DATABASE_URL`` at an empty database of
either kind is all it takes to run from source. One mechanism rather than two,
because ``create_all`` cannot alter an existing table and a second mechanism
would disagree with the migrations sooner or later.

The long block of hand-written ``ALTER TABLE`` statements that used to live here
was retired when the Alembic baseline landed: it detected columns with ``PRAGMA
table_info``, declared ``BOOLEAN DEFAULT 0``, and compared ``is_builtin = 1``,
none of which Postgres accepts.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event, inspect, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.config import settings
from app.db.base import Base

# Migrating on startup suits a single-replica deployment. Turn it off and run
# "alembic upgrade head" as a separate step if several replicas start at once,
# since they would otherwise race to apply the same revision.
AUTO_MIGRATE = os.environ.get("TYPECAST_AUTO_MIGRATE", "1") != "0"

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Turn on SQLite foreign keys, which default to off on every connection.

    Gated on the dialect: this fired unconditionally before, so ``PRAGMA`` was
    sent to Postgres and the first connection failed with a syntax error.
    """
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create or upgrade the schema, then seed. Safe to run on every start."""
    # Register every table before anything inspects Base.metadata. init_db used
    # to rely on the caller having imported the models first, which main.py does
    # by accident (it imports the routers) and a direct caller does not.
    import app.models  # noqa: F401

    if AUTO_MIGRATE:
        await _migrate_to_head()
    else:
        logger.warning(
            "TYPECAST_AUTO_MIGRATE=0: run 'alembic upgrade head' yourself before serving"
        )

    await _seed_profiles()
    await _sync_builtin_profile_metrics()
    await _backfill_user_ownership()
    await _bootstrap_admin()


def _alembic_config(connection) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # env.py uses this instead of building its own engine: we are already inside
    # a running event loop, where a second asyncio.run() would fail.
    config.attributes["connection"] = connection
    return config


def _upgrade_or_adopt(connection) -> None:
    """Bring the schema to head, adopting a database created before Alembic.

    Three cases. An empty database gets every table from the baseline. A
    database already under Alembic gets any newer revisions. A database with our
    tables but no ``alembic_version`` predates the baseline, so it is stamped
    rather than upgraded, because replaying the baseline would fail on tables
    that already exist. Development databases from before the Alembic switch are
    in that third state.
    """
    context = MigrationContext.configure(connection)
    current = context.get_current_revision()
    head = ScriptDirectory.from_config(_alembic_config(connection)).get_current_head()

    if current is not None:
        if current == head:
            logger.debug("Schema already at head (%s)", head)
        else:
            logger.info("Upgrading schema %s -> %s", current, head)
        command.upgrade(_alembic_config(connection), "head")
        return

    existing = set(inspect(connection).get_table_names())
    expected = set(Base.metadata.tables)
    if existing & expected:
        logger.warning(
            "Database has %d of our tables but no alembic_version; stamping as %s "
            "instead of re-creating them",
            len(existing & expected), head,
        )
        command.stamp(_alembic_config(connection), "head")
        return

    logger.info("Empty database: creating schema at revision %s", head)
    command.upgrade(_alembic_config(connection), "head")


def make_migration_engine(url: str):
    """An engine whose transactions really cover DDL, for running migrations.

    Python's sqlite3 driver does not emit BEGIN before DDL, so on the normal
    engine an ALTER TABLE runs in autocommit even inside ``engine.begin()``. A
    migration that failed partway through therefore left its earlier steps
    applied with the version unchanged, and every later startup failed on the
    half-done step. That happened to a real development database: a column and
    an index were added, the foreign key step failed, and the next run died on
    "duplicate column name". Taking transaction control from the driver and
    issuing BEGIN ourselves (SQLAlchemy's documented recipe) makes the whole
    migration roll back instead.

    Kept separate from the application engine on purpose. Applied there, every
    read would hold a SQLite lock until its session closed, and a streaming AI
    response keeps its session open for minutes.
    """
    migration_engine = create_async_engine(url)
    if migration_engine.dialect.name == "sqlite":

        @event.listens_for(migration_engine.sync_engine, "connect")
        def _take_transaction_control(dbapi_connection, connection_record):
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        @event.listens_for(migration_engine.sync_engine, "begin")
        def _begin(conn):
            conn.exec_driver_sql("BEGIN")

    return migration_engine


async def _migrate_to_head() -> None:
    migration_engine = make_migration_engine(settings.database_url)
    try:
        async with migration_engine.begin() as conn:
            await conn.run_sync(_upgrade_or_adopt)
    except Exception as exc:
        logger.error("Schema migration failed: %s", exc)
        raise RuntimeError(_connection_help(exc)) from exc
    finally:
        await migration_engine.dispose()


def _connection_help(exc: Exception) -> str:
    """Turn a driver-level failure into something actionable.

    A missing Postgres database is the common first-run mistake, and asyncpg
    reports it as InvalidCatalogNameError, which says little on its own.
    """
    name = type(exc).__name__
    text = str(exc)
    if "InvalidCatalogName" in name or ("does not exist" in text and settings.is_postgres):
        return (
            "The Postgres database in DATABASE_URL does not exist. Typecast creates "
            "its tables but not the database itself: create it first with "
            "'createdb typecast' or CREATE DATABASE, then start again. "
            f"Driver said: {text}"
        )
    if "InvalidPassword" in name or "PasswordAuthenticationFailed" in name:
        return f"Postgres rejected the credentials in DATABASE_URL. Driver said: {text}"
    if "ConnectionRefused" in name or "Connect call failed" in text:
        return (
            "Could not reach the database host in DATABASE_URL. Check the host, port, "
            f"and that TLS is required ('?sslmode=require'). Driver said: {text}"
        )
    return f"Could not prepare the database schema: {text}"


async def _bootstrap_admin() -> None:
    """Create the first admin from the environment on an empty user table."""
    from app.services.auth import ensure_admin_user

    async with async_session_factory() as session:
        await ensure_admin_user(session)


async def _sync_builtin_profile_metrics() -> None:
    """Reset margin and header/footer geometry on the built-in profiles.

    Runs every startup so corrections to the shipped defaults reach existing
    databases. Only touches ``is_builtin`` rows, so custom profiles are left
    alone, but it does mean an edit to a built-in profile's geometry does not
    survive a restart.
    """
    from app.models.profile import Profile

    footer = {"footer_recto": "page_number", "footer_verso": "page_number"}
    metrics = {
        "Paperback 6x9": dict(
            margin_top=0.875, margin_bottom=0.875,
            header_margin_top=0.25, header_from_edge=0.3,
            footer_margin_bottom=0.25, footer_from_edge=0.3,
            footer_position="outer", **footer,
        ),
        "Paperback 5.5x8.5": dict(
            margin_top=0.8, margin_bottom=0.8,
            header_margin_top=0.2, header_from_edge=0.3,
            footer_margin_bottom=0.2, footer_from_edge=0.3,
            footer_position="center", **footer,
        ),
        "Hardback 6x9": dict(
            margin_top=1.0, margin_bottom=1.0,
            header_margin_top=0.3, header_from_edge=0.35,
            footer_margin_bottom=0.3, footer_from_edge=0.35,
            footer_position="outer", **footer,
        ),
    }
    async with async_session_factory() as session:
        for name, values in metrics.items():
            # ORM update rather than raw SQL: the old statement compared
            # "is_builtin = 1", which Postgres rejects for a boolean column.
            await session.execute(
                update(Profile)
                .where(Profile.name == name, Profile.is_builtin.is_(True))
                .values(**values)
            )
        await session.commit()
    logger.debug("Built-in profile geometry synced (%d profiles)", len(metrics))


async def _seed_profiles() -> None:
    from sqlalchemy import select

    from app.models.profile import Profile, ProfileFormat

    builtin = [
        {
            "name": "Standard ePub",
            "format": ProfileFormat.EPUB,
            "description": "Default ebook format for e-readers",
            "is_builtin": True,
            "font_family": "Georgia, serif",
            "font_size": "1em",
            "line_height": 1.5,
            "include_cover": True,
            "include_toc": True,
        },
        {
            "name": "Paperback 6x9",
            "format": ProfileFormat.PDF,
            "description": "Standard trade paperback",
            "is_builtin": True,
            "page_width": 6.0,
            "page_height": 9.0,
            "margin_top": 0.875,
            "margin_bottom": 0.875,
            "margin_inner": 0.875,
            "margin_outer": 0.625,
            "header_margin_top": 0.25,
            "header_from_edge": 0.3,
            "footer_margin_bottom": 0.25,
            "footer_from_edge": 0.3,
            "font_family": "Garamond, serif",
            "font_size": "11pt",
            "line_height": 1.5,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "outside",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "outer",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "outer",
        },
        {
            "name": "Paperback 5.5x8.5",
            "format": ProfileFormat.PDF,
            "description": "Digest-size paperback (B&N Press, KDP)",
            "is_builtin": True,
            "page_width": 5.5,
            "page_height": 8.5,
            "margin_top": 0.8,
            "margin_bottom": 0.8,
            "margin_inner": 0.75,
            "margin_outer": 0.5,
            "header_margin_top": 0.2,
            "header_from_edge": 0.3,
            "footer_margin_bottom": 0.2,
            "footer_from_edge": 0.3,
            "font_family": "Garamond, serif",
            "font_size": "11pt",
            "line_height": 1.4,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "center",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "center",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "center",
        },
        {
            "name": "Hardback 6x9",
            "format": ProfileFormat.PDF,
            "description": "Standard hardcover",
            "is_builtin": True,
            "page_width": 6.0,
            "page_height": 9.0,
            "margin_top": 1.0,
            "margin_bottom": 1.0,
            "margin_inner": 1.0,
            "margin_outer": 0.75,
            "header_margin_top": 0.3,
            "header_from_edge": 0.35,
            "footer_margin_bottom": 0.3,
            "footer_from_edge": 0.35,
            "font_family": "Garamond, serif",
            "font_size": "12pt",
            "line_height": 1.5,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "outside",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "outer",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "outer",
        },
    ]

    async with async_session_factory() as session:
        result = await session.execute(
            select(Profile).where(Profile.is_builtin.is_(True))
        )
        existing = {p.name for p in result.scalars().all()}
        for profile_data in builtin:
            if profile_data["name"] not in existing:
                session.add(Profile(**profile_data))
        await session.commit()


async def _backfill_user_ownership() -> None:
    """Assign unowned records to the local user if in local auth mode."""
    from app.models.codex import CodexEntry
    from app.models.conversation import Conversation
    from app.models.series import Series
    from app.models.work import Work
    from app.services.auth import AUTH_MODE, get_or_create_local_user

    if AUTH_MODE != "local":
        logger.debug("Skipping ownership backfill: auth mode is %s", AUTH_MODE)
        return

    async with async_session_factory() as session:
        user = await get_or_create_local_user(session)
        # ORM updates bind the UUID itself. The old raw SQL passed user.id.hex,
        # a 32-character string that matches SQLite's CHAR(32) rendering but not
        # a Postgres uuid column.
        # CodexEntry: entries made with no work or series have no other owner.
        for model in (Series, Work, Conversation, CodexEntry):
            result = await session.execute(
                update(model).where(model.user_id.is_(None)).values(user_id=user.id)
            )
            if result.rowcount:
                logger.info(
                    "Backfilled %d unowned %s rows to the local user",
                    result.rowcount,
                    model.__tablename__,
                )
        await session.commit()
