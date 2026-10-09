"""Shared pytest fixtures: isolated in-memory DB, app with overridden deps, async client."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import every model module so Base.metadata knows all tables before create_all.
import app.models  # noqa: F401
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.engine import get_db
from app.main import create_app
from app.models.user import User
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def engine():
    """A fresh in-memory SQLite engine per test, with all tables created.

    Foreign keys are switched on to match production. SQLite ignores
    ``ondelete`` clauses unless the pragma is set, so without this the suite
    could not observe cascade deletes at all, while Postgres always enforces
    them. That gap hid the fact that deleting a user cascades away every work,
    series, and conversation they own.
    """
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(eng.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(session_factory) -> User:
    """A persisted user that owns test-created works/series."""
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="tester@typecast.local",
            username="tester",
            display_name="Tester",
            hashed_password=hash_password("password123"),
            is_admin=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def client(session_factory, test_user) -> AsyncGenerator[AsyncClient, None]:
    """Async client bound to the app with DB and auth dependencies overridden."""
    test_app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    async def override_get_current_user() -> User:
        return test_user

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    test_app.dependency_overrides.clear()
