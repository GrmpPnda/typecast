"""Brute-force protection on password checks.

The unit tests drive the throttle with a fake clock; the endpoint tests go
through the real sign-in route in multi-user mode.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.main import create_app
from app.services import throttle
from app.services.throttle import WINDOW_SECONDS, FailureThrottle, Limits, ThrottledError


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _throttle(**limits) -> tuple[FailureThrottle, Clock]:
    clock = Clock()
    return FailureThrottle(Limits(**limits), clock=clock), clock


def _fail(t: FailureThrottle, n: int, account="a@x", client="1.1.1.1"):
    for _ in range(n):
        t.check(account, client)
        t.record_failure(account, client)


# --- the throttle itself ------------------------------------------------------------


def test_an_account_is_refused_after_its_limit_from_one_client():
    t, _ = _throttle(per_account_and_client=3, per_account=100, per_client=100)
    _fail(t, 3)
    with pytest.raises(ThrottledError):
        t.check("a@x", "1.1.1.1")


def test_refusal_lifts_as_failures_age_out_of_the_window():
    t, clock = _throttle(per_account_and_client=3, per_account=100, per_client=100)
    _fail(t, 3)
    with pytest.raises(ThrottledError) as exc:
        t.check("a@x", "1.1.1.1")
    assert exc.value.retry_after == WINDOW_SECONDS
    clock.now += exc.value.retry_after
    t.check("a@x", "1.1.1.1")


def test_spreading_guesses_across_addresses_still_hits_the_account_limit():
    """The address is forgeable behind a trusting proxy; the account limit is not."""
    t, _ = _throttle(per_account_and_client=100, per_account=4, per_client=100)
    for i in range(4):
        _fail(t, 1, client=f"10.0.0.{i}")
    with pytest.raises(ThrottledError):
        t.check("a@x", "10.0.0.99")


def test_one_address_trying_many_accounts_hits_the_client_limit():
    t, _ = _throttle(per_account_and_client=100, per_account=100, per_client=4)
    for i in range(4):
        _fail(t, 1, account=f"user{i}@x")
    with pytest.raises(ThrottledError):
        t.check("someone-new@x", "1.1.1.1")
    t.check("someone-new@x", "2.2.2.2")


def test_account_names_are_matched_case_insensitively():
    t, _ = _throttle(per_account_and_client=2, per_account=100, per_client=100)
    _fail(t, 1, account="Author@Example.com")
    _fail(t, 1, account="author@example.com ")
    with pytest.raises(ThrottledError):
        t.check("AUTHOR@example.com", "1.1.1.1")


def test_success_clears_the_account_but_not_the_client():
    """Otherwise a guesser could reset their address limit with their own account."""
    t, _ = _throttle(per_account_and_client=3, per_account=100, per_client=3)
    _fail(t, 2, account="victim@x")
    t.record_success("mine@x", "1.1.1.1")
    _fail(t, 1, account="victim@x")
    with pytest.raises(ThrottledError):
        t.check("victim@x", "1.1.1.1")


def test_memory_is_bounded_under_a_flood_of_invented_accounts(monkeypatch):
    t, _ = _throttle()
    monkeypatch.setattr(FailureThrottle, "MAX_KEYS", 50)
    for i in range(500):
        t.record_failure(f"nobody{i}@x", f"10.0.{i // 256}.{i % 256}")
    assert len(t._failures) <= 50


def test_the_message_says_when_to_try_again():
    assert throttle.retry_message(30) == "Too many failed sign-in attempts. Try again in a minute."
    assert throttle.retry_message(14 * 60 + 1) == (
        "Too many failed sign-in attempts. Try again in 15 minutes."
    )


# --- through the sign-in endpoint ------------------------------------------------------


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


def _login(email="tester@typecast.local", password="wrong-password"):
    return {"email": email, "password": password}


async def test_sign_in_is_refused_once_the_limit_is_reached(
    session_factory, test_user, monkeypatch
):
    _multi_mode(monkeypatch)
    limit = throttle.password_checks.limits.per_account_and_client
    async with _client(session_factory) as ac:
        for _ in range(limit):
            assert (await ac.post("/api/auth/login", json=_login())).status_code == 401
        refused = await ac.post("/api/auth/login", json=_login())
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) > 0
        assert "Too many failed sign-in attempts" in refused.json()["detail"]

        # The right password is refused too: being refused must not reveal
        # whether a guess was correct.
        right = await ac.post("/api/auth/login", json=_login(password="password123"))
        assert right.status_code == 429


async def test_unknown_accounts_are_throttled_like_real_ones(session_factory, monkeypatch):
    """A different answer for unknown emails would reveal which accounts exist."""
    _multi_mode(monkeypatch)
    limit = throttle.password_checks.limits.per_account_and_client
    async with _client(session_factory) as ac:
        for _ in range(limit):
            await ac.post("/api/auth/login", json=_login(email="ghost@typecast.local"))
        resp = await ac.post("/api/auth/login", json=_login(email="ghost@typecast.local"))
    assert resp.status_code == 429


async def test_a_successful_sign_in_resets_the_count(session_factory, test_user, monkeypatch):
    _multi_mode(monkeypatch)
    limit = throttle.password_checks.limits.per_account_and_client
    async with _client(session_factory) as ac:
        for _ in range(limit - 1):
            await ac.post("/api/auth/login", json=_login())
        ok = await ac.post("/api/auth/login", json=_login(password="password123"))
        assert ok.status_code == 200
        for _ in range(limit - 1):
            assert (await ac.post("/api/auth/login", json=_login())).status_code == 401


async def test_password_change_shares_the_limit(session_factory, test_user, monkeypatch):
    """A stolen token must not allow unlimited guesses at the current password."""
    _multi_mode(monkeypatch)
    limit = throttle.password_checks.limits.per_account_and_client
    async with _client(session_factory) as ac:
        token = (await ac.post("/api/auth/login", json=_login(password="password123"))).json()[
            "token"
        ]
        headers = {"Authorization": f"Bearer {token}"}
        body = {"current_password": "guess-guess", "new_password": "new-password-123"}
        for _ in range(limit):
            resp = await ac.put("/api/auth/me/password", json=body, headers=headers)
            assert resp.status_code == 403
        resp = await ac.put("/api/auth/me/password", json=body, headers=headers)
        assert resp.status_code == 429
        signed_in = await ac.post("/api/auth/login", json=_login(password="password123"))
        assert signed_in.status_code == 429
