from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import settings
from app.db.base import Base
from app.models import *  # noqa: F401, F403

config = context.config
# settings.database_url, not the raw DATABASE_URL, so Alembic gets the same
# asyncpg driver and ssl= corrections the application connects with. The % is
# escaped because set_main_option writes through ConfigParser, which treats a
# bare % as interpolation and chokes on generated Postgres passwords.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# Only configure logging for the alembic CLI. When the app migrates on startup
# it hands in a connection, and fileConfig would replace the app's handlers and,
# by default, disable every logger that already exists: all request logging and
# every unhandled-exception traceback went silent after the first startup.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    # The application runs migrations at startup and hands in its own
    # connection, because it is already inside a running event loop and
    # asyncio.run() would refuse to start a second one.
    injected = config.attributes.get("connection")
    if injected is not None:
        do_run_migrations(injected)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
