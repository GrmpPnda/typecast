"""Tests for auth: password hashing, token lifecycle, and protected-route enforcement."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.main import create_app
from app.services.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert verify_password("hunter2", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip(test_user):
    token = create_access_token(test_user.id)
    assert decode_access_token(token) == test_user.id


def test_tampered_token_rejected(test_user):
    token = create_access_token(test_user.id)
    tampered = token[:-4] + ("0000" if not token.endswith("0000") else "1111")
    assert decode_access_token(tampered) is None


def test_garbage_token_rejected():
    assert decode_access_token("not-a-real-token") is None


@pytest_asyncio.fixture
async def raw_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Client with only get_db overridden — real auth dependency active."""
    test_app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    test_app.dependency_overrides.clear()


async def test_me_with_valid_token(raw_client, test_user):
    token = create_access_token(test_user.id)
    resp = await raw_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    # In local auth mode the dependency may auto-return a user; in multi mode it
    # validates the token. Either way a valid token must succeed.
    assert resp.status_code == 200
    assert "email" in resp.json()
