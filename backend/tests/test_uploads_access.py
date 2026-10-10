"""Uploaded files are served only to the accounts they belong to.

Real authentication throughout (multi-user mode, real tokens), because the
property under test is who the server lets in.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import files
from app.db.engine import get_db
from app.main import create_app
from app.models.codex import CodexEntry, EntryType
from app.models.series import Series
from app.models.user import User
from app.models.work import Work
from app.services.auth import UPLOADS_COOKIE, create_access_token, hash_password


def _multi_mode(monkeypatch):
    for module in ("app.services.auth", "app.api.auth", "app.api.deps"):
        monkeypatch.setattr(f"{module}.AUTH_MODE", "multi", raising=False)
        monkeypatch.setattr(f"{module}.NO_AUTOLOGIN", False, raising=False)


def _client(session_factory) -> AsyncClient:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://typecast.example")


@pytest.fixture
async def library(session_factory, tmp_path, monkeypatch):
    """Alice owns a work, a series, and a codex entry, each with a file; a font is shared."""
    _multi_mode(monkeypatch)
    monkeypatch.setattr(files, "UPLOAD_DIR", tmp_path)

    alice, bob = (
        User(id=uuid.uuid4(), email=f"{n}@example.com", username=n, display_name=n,
             hashed_password=hash_password("x" * 12))
        for n in ("alice", "bob")
    )
    work = Work(id=uuid.uuid4(), title="Hers", author="A", user_id=alice.id,
                cover_image_path="/uploads/covers/work-cover.png")
    series = Series(id=uuid.uuid4(), title="Saga", user_id=alice.id,
                    cover_image_path="/uploads/covers/series-cover.png")
    entry = CodexEntry(id=uuid.uuid4(), name="Hero", entry_type=EntryType.CHARACTER,
                       user_id=alice.id)
    async with session_factory() as session:
        session.add_all([alice, bob])
        await session.commit()
        session.add_all([work, series, entry])
        await session.commit()

    urls = {
        "image": f"images/{work.id}/scene.png",
        "codex": f"codex/{entry.id}/portrait.png",
        "work_cover": "covers/work-cover.png",
        "series_cover": "covers/series-cover.png",
        "font": "fonts/Garamond.ttf",
    }
    for relative in urls.values():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"file:" + relative.encode())
    (tmp_path / "covers" / "orphan.png").write_bytes(b"nobody's")
    return alice, bob, {k: f"/uploads/{v}" for k, v in urls.items()}


def _bearer(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


OWNED = ["image", "codex", "work_cover", "series_cover"]


async def test_nothing_is_served_without_signing_in(session_factory, library):
    _alice, _bob, urls = library
    async with _client(session_factory) as ac:
        for url in urls.values():
            assert (await ac.get(url)).status_code == 401, url


@pytest.mark.parametrize("name", OWNED)
async def test_the_owner_can_read_their_files(session_factory, library, name):
    alice, _bob, urls = library
    async with _client(session_factory) as ac:
        resp = await ac.get(urls[name], headers=_bearer(alice))
    assert resp.status_code == 200
    assert resp.content.startswith(b"file:")
    assert "private" in resp.headers["cache-control"]


@pytest.mark.parametrize("name", OWNED)
async def test_another_account_is_told_the_file_does_not_exist(session_factory, library, name):
    _alice, bob, urls = library
    async with _client(session_factory) as ac:
        assert (await ac.get(urls[name], headers=_bearer(bob))).status_code == 404


async def test_fonts_are_readable_by_every_account(session_factory, library):
    alice, bob, urls = library
    async with _client(session_factory) as ac:
        for user in (alice, bob):
            assert (await ac.get(urls["font"], headers=_bearer(user))).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/uploads/covers/orphan.png",  # a cover no work or series uses
        "/uploads/images/not-a-uuid/scene.png",
        "/uploads/somewhere/else.png",
        "/uploads/covers/missing.png",
        "/uploads/images/{work}/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
        "/uploads/fonts/%2e%2e/covers/work-cover.png",
    ],
)
async def test_unknown_unowned_and_escaping_paths_are_not_found(session_factory, library, path):
    alice, _bob, urls = library
    work_id = urls["image"].split("/")[3]
    async with _client(session_factory) as ac:
        resp = await ac.get(path.format(work=work_id), headers=_bearer(alice))
    assert resp.status_code == 404


async def test_the_browser_reads_uploads_with_the_session_cookie(session_factory, library):
    alice, bob, urls = library
    async with _client(session_factory) as ac:
        opened = await ac.post("/api/auth/session", headers=_bearer(alice))
        assert opened.status_code == 204
        cookie = opened.headers["set-cookie"]
        for attribute in ("HttpOnly", "Path=/uploads", "SameSite=lax", "Secure"):
            assert attribute.lower() in cookie.lower(), f"{attribute} missing: {cookie}"

        # No header: the cookie alone, as an <img> request would send it.
        assert (await ac.get(urls["image"])).status_code == 200

        closed = await ac.delete("/api/auth/session")
        assert closed.status_code == 204
        assert (await ac.get(urls["image"])).status_code == 401


async def test_the_uploads_cookie_never_authenticates_the_api(session_factory, library):
    """A cookie that worked on the API would let any website act as the user."""
    alice, _bob, _urls = library
    token = create_access_token(alice.id)
    async with _client(session_factory) as ac:
        for name in (UPLOADS_COOKIE, "token"):
            resp = await ac.get("/api/works/", headers={"Cookie": f"{name}={token}"})
            assert resp.status_code == 401, f"{name} cookie authenticated the API"
        # And the bearer token still does.
        assert (await ac.get("/api/works/", headers=_bearer(alice))).status_code == 200


async def test_opening_a_session_needs_a_signed_in_account(session_factory, library):
    async with _client(session_factory) as ac:
        assert (await ac.post("/api/auth/session")).status_code == 401
