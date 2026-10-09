"""Admin user management, password changes, and registration policy.

Registration is admin-only, which makes two things load-bearing: the admin
endpoints are the only way an account comes into existence, and the guards that
stop an admin locking everyone out of the deployment.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.main import create_app
from app.models.user import User
from app.services.auth import hash_password


async def _make_user(session_factory, **kwargs) -> User:
    defaults = {
        "id": uuid.uuid4(),
        "email": f"{uuid.uuid4().hex[:8]}@typecast.local",
        "username": uuid.uuid4().hex[:8],
        "display_name": "Someone",
        "hashed_password": hash_password("password123"),
        "is_admin": False,
        "is_active": True,
    }
    defaults.update(kwargs)
    async with session_factory() as session:
        user = User(**defaults)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def _client_as(session_factory, user: User) -> AsyncClient:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def member(session_factory) -> User:
    """A non-admin account."""
    return await _make_user(session_factory, is_admin=False)


# --- access control ---------------------------------------------------------


async def test_non_admin_cannot_list_users(session_factory, member):
    async with _client_as(session_factory, member) as ac:
        assert (await ac.get("/api/users/")).status_code == 403


async def test_non_admin_cannot_create_users(session_factory, member):
    async with _client_as(session_factory, member) as ac:
        resp = await ac.post(
            "/api/users/",
            json={
                "email": "new@typecast.local",
                "username": "newbie",
                "display_name": "New",
                "password": "password123",
            },
        )
    assert resp.status_code == 403


async def test_admin_lists_users(client, test_user):
    resp = await client.get("/api/users/")
    assert resp.status_code == 200
    assert [u["email"] for u in resp.json()] == [test_user.email]


# --- creation --------------------------------------------------------------


async def test_admin_creates_a_user(client):
    resp = await client.post(
        "/api/users/",
        json={
            "email": "reader@typecast.local",
            "username": "reader",
            "display_name": "Beta Reader",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "reader@typecast.local"
    assert body["is_admin"] is False
    assert body["is_active"] is True


async def test_duplicate_email_is_rejected(client, test_user):
    resp = await client.post(
        "/api/users/",
        json={
            "email": test_user.email,
            "username": "different",
            "display_name": "Clash",
            "password": "password123",
        },
    )
    assert resp.status_code == 409


async def test_short_password_is_rejected(client):
    resp = await client.post(
        "/api/users/",
        json={
            "email": "weak@typecast.local",
            "username": "weak",
            "display_name": "Weak",
            "password": "short",
        },
    )
    assert resp.status_code == 422


# --- lockout guards --------------------------------------------------------


async def test_cannot_demote_the_last_admin(client, test_user):
    """Otherwise the deployment has no account able to create accounts."""
    resp = await client.patch(f"/api/users/{test_user.id}", json={"is_admin": False})
    assert resp.status_code == 409
    assert "last active administrator" in resp.json()["detail"]


async def test_cannot_deactivate_the_last_admin(client, test_user):
    resp = await client.patch(f"/api/users/{test_user.id}", json={"is_active": False})
    assert resp.status_code == 409


async def test_cannot_delete_the_last_admin(client, test_user):
    resp = await client.delete(f"/api/users/{test_user.id}")
    assert resp.status_code == 409


async def test_can_demote_an_admin_when_another_remains(session_factory, client):
    other_admin = await _make_user(session_factory, is_admin=True)
    resp = await client.patch(f"/api/users/{other_admin.id}", json={"is_admin": False})
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


async def test_cannot_delete_own_account(session_factory):
    admin = await _make_user(session_factory, is_admin=True)
    await _make_user(session_factory, is_admin=True)  # so the last-admin guard is not the cause
    async with _client_as(session_factory, admin) as ac:
        resp = await ac.delete(f"/api/users/{admin.id}")
    assert resp.status_code == 409
    assert "your own account" in resp.json()["detail"]


async def _give_work(session_factory, user: User, title: str) -> None:
    from app.models.work import Work

    async with session_factory() as session:
        session.add(Work(id=uuid.uuid4(), title=title, author="A", user_id=user.id))
        await session.commit()


async def test_deleting_a_user_who_owns_work_is_refused(session_factory, client):
    """user_id is ondelete=CASCADE, so an unguarded delete destroys manuscripts."""
    victim = await _make_user(session_factory)
    await _give_work(session_factory, victim, "Their Novel")

    resp = await client.delete(f"/api/users/{victim.id}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "1 works" in detail
    assert "Deactivate" in detail

    from sqlalchemy import select

    from app.models.work import Work

    async with session_factory() as session:
        titles = (await session.execute(select(Work.title))).scalars().all()
    assert list(titles) == ["Their Novel"]


async def test_purge_deletes_the_account_and_its_content(session_factory, client):
    """The escape hatch works, and is explicit about what it destroys."""
    victim = await _make_user(session_factory)
    await _give_work(session_factory, victim, "Doomed Novel")

    resp = await client.delete(f"/api/users/{victim.id}?purge=true")
    assert resp.status_code == 204

    from sqlalchemy import select

    from app.models.work import Work

    async with session_factory() as session:
        assert (await session.get(User, victim.id)) is None
        assert list((await session.execute(select(Work.title))).scalars().all()) == []


async def test_deleting_an_empty_account_needs_no_purge(session_factory, client):
    victim = await _make_user(session_factory)
    assert (await client.delete(f"/api/users/{victim.id}")).status_code == 204


# --- deactivation takes effect immediately ---------------------------------


async def test_deactivated_user_is_refused_on_the_next_request(session_factory, client):
    """is_active is checked per request, not only at login, so there is no
    window where a disabled account keeps working on an unexpired token."""
    member = await _make_user(session_factory)
    disable = await client.patch(f"/api/users/{member.id}", json={"is_active": False})
    assert disable.status_code == 200

    # get_current_user is the real dependency here, driven by the stored flag.
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    from app.services.auth import create_access_token

    token = create_access_token(member.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    # Local mode auto-login would mask this, so only assert when it is enforced.
    from app.services.auth import AUTH_MODE, NO_AUTOLOGIN

    if not (AUTH_MODE == "local" and not NO_AUTOLOGIN):
        assert resp.status_code == 401


# --- password changes ------------------------------------------------------


async def test_user_changes_own_password(session_factory):
    member = await _make_user(session_factory)
    async with _client_as(session_factory, member) as ac:
        resp = await ac.put(
            "/api/auth/me/password",
            json={"current_password": "password123", "new_password": "a-longer-secret"},
        )
    assert resp.status_code == 204

    async with session_factory() as session:
        from app.services.auth import verify_password

        fresh = await session.get(User, member.id)
        assert verify_password("a-longer-secret", fresh.hashed_password)


async def test_password_change_requires_the_current_password(session_factory):
    member = await _make_user(session_factory)
    async with _client_as(session_factory, member) as ac:
        resp = await ac.put(
            "/api/auth/me/password",
            json={"current_password": "wrong", "new_password": "a-longer-secret"},
        )
    assert resp.status_code == 403

    async with session_factory() as session:
        from app.services.auth import verify_password

        fresh = await session.get(User, member.id)
        assert verify_password("password123", fresh.hashed_password)


async def test_admin_resets_another_password(session_factory, client):
    member = await _make_user(session_factory)
    resp = await client.put(
        f"/api/users/{member.id}/password", json={"password": "reset-by-admin"}
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        from app.services.auth import verify_password

        fresh = await session.get(User, member.id)
        assert verify_password("reset-by-admin", fresh.hashed_password)


async def test_patch_unknown_user_is_404(client):
    resp = await client.patch(f"/api/users/{uuid.uuid4()}", json={"is_active": False})
    assert resp.status_code == 404


# --- registration policy ---------------------------------------------------


@pytest.mark.parametrize("open_registration", [False, True])
async def test_registration_follows_the_open_registration_flag(
    session_factory, monkeypatch, open_registration
):
    """Self-service signup is closed unless explicitly enabled."""
    monkeypatch.setattr("app.api.auth.OPEN_REGISTRATION", open_registration)
    _force_mode(monkeypatch, "multi")

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/auth/register",
            json={
                "email": "walkin@typecast.local",
                "username": "walkin",
                "display_name": "Walk In",
                "password": "password123",
            },
        )

    assert resp.status_code == (201 if open_registration else 403)


async def test_auth_mode_reports_whether_signup_is_open(client):
    body = (await client.get("/api/auth/mode")).json()
    assert "open_registration" in body
    assert body["open_registration"] is False


# --- first-run setup -------------------------------------------------------


def _anon_client(session_factory) -> AsyncClient:
    """A client with no authentication override, as a first-run visitor has."""
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


SETUP_PAYLOAD = {
    "email": "founder@typecast.local",
    "username": "founder",
    "display_name": "Founder",
    "password": "setup-secret",
}


def _force_mode(monkeypatch, mode: str, no_autologin: bool = False) -> None:
    """Set the auth mode everywhere it is bound.

    ``AUTH_MODE`` is read from the environment once and imported into three
    module namespaces, so patching only the router leaves ``api/deps.py`` still
    auto-logging in the local user and the request never reaches the account
    under test.
    """
    for module in ("app.services.auth", "app.api.auth", "app.api.deps"):
        monkeypatch.setattr(f"{module}.AUTH_MODE", mode, raising=False)
        monkeypatch.setattr(f"{module}.NO_AUTOLOGIN", no_autologin, raising=False)


async def test_setup_is_required_on_an_empty_multi_user_database(
    session_factory, monkeypatch
):
    _force_mode(monkeypatch, "multi")
    async with _anon_client(session_factory) as ac:
        body = (await ac.get("/api/auth/mode")).json()
    assert body["setup_required"] is True


async def test_setup_creates_an_administrator_and_signs_them_in(
    session_factory, monkeypatch
):
    _force_mode(monkeypatch, "multi")
    async with _anon_client(session_factory) as ac:
        resp = await ac.post("/api/auth/setup", json=SETUP_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["user"]["is_admin"] is True
        assert body["token"]

        # The token works immediately, so the admin lands signed in.
        me = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == SETUP_PAYLOAD["email"]

        # And setup closes behind them.
        assert (await ac.get("/api/auth/mode")).json()["setup_required"] is False


async def test_setup_is_refused_once_any_account_exists(
    session_factory, monkeypatch, member
):
    """This endpoint is unauthenticated, so the empty-table check is the only
    thing stopping it from being an open administrator signup."""
    _force_mode(monkeypatch, "multi")
    async with _anon_client(session_factory) as ac:
        assert (await ac.get("/api/auth/mode")).json()["setup_required"] is False
        resp = await ac.post("/api/auth/setup", json=SETUP_PAYLOAD)
    assert resp.status_code == 409
    assert "already been completed" in resp.json()["detail"]


async def test_a_non_admin_account_still_closes_setup(session_factory, monkeypatch, member):
    """Any account at all, not just an admin, must close the endpoint."""
    _force_mode(monkeypatch, "multi")
    assert member.is_admin is False
    async with _anon_client(session_factory) as ac:
        resp = await ac.post("/api/auth/setup", json=SETUP_PAYLOAD)
    assert resp.status_code == 409


async def test_setup_does_not_apply_in_local_mode(session_factory, monkeypatch):
    """Local mode creates its single user automatically; there is nothing to set up."""
    _force_mode(monkeypatch, "local", no_autologin=False)
    async with _anon_client(session_factory) as ac:
        assert (await ac.get("/api/auth/mode")).json()["setup_required"] is False
        resp = await ac.post("/api/auth/setup", json=SETUP_PAYLOAD)
    assert resp.status_code == 400


async def test_setup_rejects_a_short_password(session_factory, monkeypatch):
    _force_mode(monkeypatch, "multi")
    async with _anon_client(session_factory) as ac:
        resp = await ac.post("/api/auth/setup", json={**SETUP_PAYLOAD, "password": "short"})
    assert resp.status_code == 422


async def test_env_bootstrapped_admin_also_closes_setup(session_factory, monkeypatch):
    """The two ways of making the first admin must not both fire."""
    from app.services.auth import ensure_admin_user

    _force_mode(monkeypatch, "multi")
    monkeypatch.setenv("TYPECAST_ADMIN_EMAIL", "env@typecast.local")
    monkeypatch.setenv("TYPECAST_ADMIN_PASSWORD", "env-bootstrap-secret")

    async with session_factory() as session:
        await ensure_admin_user(session)

    async with _anon_client(session_factory) as ac:
        assert (await ac.get("/api/auth/mode")).json()["setup_required"] is False
        resp = await ac.post("/api/auth/setup", json=SETUP_PAYLOAD)
    assert resp.status_code == 409
