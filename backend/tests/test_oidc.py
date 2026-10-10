"""Signing in with Microsoft or Google, run by Typecast itself.

A fake identity provider with real RSA keys answers discovery, keys, and token
requests, so every ID token in these tests is genuinely signed and genuinely
verified. Nothing reaches a real provider.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.main import create_app
from app.models.user import User
from app.services import accounts, oidc
from app.services.auth import hash_password

TENANT = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT = "99999999-8888-7777-6666-555555555555"
KID = "fake-key"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ATTACKER = rsa.generate_private_key(public_exponent=65537, key_size=2048)

MICROSOFT = oidc.Provider(
    id="microsoft", name="Microsoft", client_id="ms-client", client_secret="ms-secret",
    discovery_url="https://login.microsoftonline.com/x/v2.0/.well-known/openid-configuration",
    tenant=TENANT,
)
GOOGLE = oidc.Provider(
    id="google", name="Google", client_id="g-client", client_secret="g-secret",
    discovery_url="https://accounts.google.com/.well-known/openid-configuration",
)


class FakeProvider:
    """Answers whatever oidc.py asks the provider, and records the token requests."""

    def __init__(self):
        self.claims: dict = {}
        self.key = PRIVATE
        self.token_requests: list[dict] = []
        self.refuse_code = False

    def mint(self, nonce: str) -> str:
        now = int(time.time())
        body = {"iat": now, "exp": now + 3600, "nonce": nonce, **self.claims}
        return jwt.encode(body, self.key, algorithm="RS256", headers={"kid": KID})


class FakeClient:
    def __init__(self, provider: FakeProvider):
        self.p = provider

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        if url.endswith("openid-configuration"):
            body = {
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "jwks_uri": "https://idp.example/keys",
            }
        else:
            jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE.public_key(), as_dict=True)
            body = {"keys": [{**jwk, "kid": KID, "use": "sig"}]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    async def post(self, url, data=None, headers=None):
        self.p.token_requests.append(dict(data or {}))
        request = httpx.Request("POST", url)
        if self.p.refuse_code:
            return httpx.Response(400, json={"error": "invalid_grant"}, request=request)
        return httpx.Response(200, json={"id_token": self.p.mint(self.p.nonce)}, request=request)


@pytest.fixture
def idp(monkeypatch):
    provider = FakeProvider()
    oidc.reset()
    monkeypatch.setattr(oidc, "PROVIDERS", {"microsoft": MICROSOFT, "google": GOOGLE})
    monkeypatch.setattr(oidc, "_client", lambda: FakeClient(provider))
    monkeypatch.setattr(oidc, "PUBLIC_URL", "")
    for module in ("app.services.auth", "app.api.auth", "app.api.deps"):
        monkeypatch.setattr(f"{module}.AUTH_MODE", "multi", raising=False)
        monkeypatch.setattr(f"{module}.NO_AUTOLOGIN", False, raising=False)
    monkeypatch.setattr("app.services.auth.OPEN_REGISTRATION", False)
    yield provider
    oidc.reset()


def _client(session_factory) -> AsyncClient:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://typecast.example")


def _microsoft(oid="oid-1", email="author@example.com", tid=TENANT, **extra) -> dict:
    return {
        "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "aud": MICROSOFT.client_id,
        "sub": f"pairwise-{oid}", "oid": oid, "tid": tid, "preferred_username": email,
        "name": "Author", **extra,
    }


def _google(sub="g-1", email="author@example.com", verified=True, **extra) -> dict:
    return {
        "iss": "https://accounts.google.com", "aud": GOOGLE.client_id, "sub": sub,
        "email": email, "email_verified": verified, "name": "Author", **extra,
    }


async def _sign_in(ac: AsyncClient, idp: FakeProvider, provider: str, claims: dict,
                   *, tamper=None) -> httpx.Response:
    """Run start → provider → callback. Returns the callback's redirect."""
    start = await ac.get(f"/api/auth/oidc/{provider}/start")
    assert start.status_code == 302, start.text
    params = parse_qs(urlsplit(start.headers["location"]).query)
    idp.nonce = params["nonce"][0]
    idp.claims = claims
    state = params["state"][0]
    query = {"code": "auth-code", "state": state}
    if tamper:
        query = tamper(query)
    return await ac.get(f"/api/auth/oidc/{provider}/callback", params=query)


def _outcome(resp: httpx.Response) -> dict[str, str]:
    assert resp.status_code == 302 and resp.headers["location"].startswith("/login?")
    return {k: v[0] for k, v in parse_qs(urlsplit(resp.headers["location"]).query).items()}


async def _session(ac: AsyncClient, resp: httpx.Response) -> dict:
    outcome = _outcome(resp)
    assert "sso_code" in outcome, outcome
    exchanged = await ac.post("/api/auth/oidc/exchange", json={"code": outcome["sso_code"]})
    assert exchanged.status_code == 200, exchanged.text
    return exchanged.json()


async def _add_user(session_factory, **fields) -> User:
    defaults = dict(id=uuid.uuid4(), username=fields["email"].split("@")[0],
                    display_name="Someone", hashed_password=hash_password("old-password-1"),
                    auth_provider="password")
    user = User(**{**defaults, **fields})
    async with session_factory() as session:
        session.add(user)
        await session.commit()
    return user


async def _get(session_factory, email) -> User:
    async with session_factory() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one()


# --- the flow ----------------------------------------------------------------------


async def test_the_server_lists_its_providers(session_factory, idp):
    async with _client(session_factory) as ac:
        body = (await ac.get("/api/auth/mode")).json()
    assert [p["id"] for p in body["providers"]] == ["microsoft", "google"]
    assert body["providers"][0]["start_url"] == "/api/auth/oidc/microsoft/start"


async def test_start_sends_a_complete_authorization_request(session_factory, idp):
    async with _client(session_factory) as ac:
        start = await ac.get("/api/auth/oidc/google/start")
    params = parse_qs(urlsplit(start.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["https://typecast.example/api/auth/oidc/google/callback"]
    assert params["scope"] == ["openid email profile"]
    assert len(params["state"][0]) >= 40 and len(params["nonce"][0]) >= 40
    cookie = start.headers["set-cookie"].lower()
    for attribute in ("httponly", "path=/api/auth/oidc", "samesite=lax", "secure"):
        assert attribute in cookie


async def test_a_full_sign_in_creates_the_first_administrator(session_factory, idp):
    async with _client(session_factory) as ac:
        session = await _session(ac, await _sign_in(ac, idp, "google", _google()))
        me = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {session['token']}"})
    assert me.status_code == 200
    assert me.json()["auth_provider"] == "google" and me.json()["is_admin"] is True
    # The code exchange carried the PKCE verifier and the client secret.
    sent = idp.token_requests[-1]
    assert sent["code_verifier"] and sent["client_secret"] == "g-secret"


async def test_the_code_is_single_use(session_factory, idp):
    async with _client(session_factory) as ac:
        outcome = _outcome(await _sign_in(ac, idp, "google", _google()))
        first = await ac.post("/api/auth/oidc/exchange", json={"code": outcome["sso_code"]})
        again = await ac.post("/api/auth/oidc/exchange", json={"code": outcome["sso_code"]})
    assert first.status_code == 200 and again.status_code == 400


async def test_a_callback_from_another_browser_is_refused(session_factory, idp):
    """Without the state cookie: someone else's link must not sign this browser in."""
    async with _client(session_factory) as ac:
        start = await ac.get("/api/auth/oidc/google/start")
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    async with _client(session_factory) as victim:
        resp = await victim.get(
            "/api/auth/oidc/google/callback", params={"code": "x", "state": state}
        )
    assert "not started in this browser" in _outcome(resp)["sso_error"]
    assert idp.token_requests == [], "the code must not even be exchanged"


async def test_a_state_works_once(session_factory, idp):
    async with _client(session_factory) as ac:
        start = await ac.get("/api/auth/oidc/google/start")
        params = parse_qs(urlsplit(start.headers["location"]).query)
        idp.nonce, idp.claims = params["nonce"][0], _google()
        query = {"code": "c", "state": params["state"][0]}
        cookie = {"Cookie": f"{oidc.STATE_COOKIE}={params['state'][0]}"}
        first = await ac.get("/api/auth/oidc/google/callback", params=query, headers=cookie)
        replay = await ac.get("/api/auth/oidc/google/callback", params=query, headers=cookie)
    assert "sso_code" in _outcome(first)
    assert "already used" in _outcome(replay)["sso_error"]


@pytest.mark.parametrize(
    ("label", "claims", "change"),
    [
        ("signed with another key", _google(), {"key": ATTACKER}),
        ("for another application", _google(aud="someone-else"), {}),
        ("from another issuer", _google(iss="https://evil.example"), {}),
        ("expired", _google(exp=int(time.time()) - 3600), {}),
        ("from another directory", _microsoft(tid=OTHER_TENANT), {"provider": "microsoft"}),
        ("with a replayed nonce", _google(nonce="not-this-sign-in"), {}),
    ],
)
async def test_forged_and_foreign_tokens_are_refused(session_factory, idp, label, claims, change):
    provider = change.get("provider", "google")
    idp.key = change.get("key", PRIVATE)
    async with _client(session_factory) as ac:
        resp = await _sign_in(ac, idp, provider, claims)
    outcome = _outcome(resp)
    assert "sso_error" in outcome and "sso_code" not in outcome, label
    async with session_factory() as session:
        assert (await session.execute(select(User))).first() is None, label


async def test_the_provider_refusing_the_code_is_reported(session_factory, idp):
    idp.refuse_code = True
    async with _client(session_factory) as ac:
        resp = await _sign_in(ac, idp, "google", _google())
    assert "did not complete the sign-in" in _outcome(resp)["sso_error"]


async def test_a_cancelled_sign_in_says_so(session_factory, idp):
    async with _client(session_factory) as ac:
        resp = await ac.get(
            "/api/auth/oidc/microsoft/callback",
            params={"error": "access_denied", "error_description": "AADSTS65004"},
        )
    assert "cancelled or not allowed" in _outcome(resp)["sso_error"]


# --- one sign-in method per account ---------------------------------------------------


async def test_strangers_are_turned_away(session_factory, idp):
    await _add_user(session_factory, email="admin@example.com", is_admin=True)
    async with _client(session_factory) as ac:
        resp = await _sign_in(ac, idp, "google", _google(email="stranger@example.com"))
    assert "Ask an administrator" in _outcome(resp)["sso_error"]


async def test_open_registration_creates_ordinary_accounts(session_factory, idp, monkeypatch):
    monkeypatch.setattr("app.services.auth.OPEN_REGISTRATION", True)
    await _add_user(session_factory, email="admin@example.com", is_admin=True)
    async with _client(session_factory) as ac:
        await _session(ac, await _sign_in(ac, idp, "google", _google(email="new@example.com")))
    new = await _get(session_factory, "new@example.com")
    assert new.auth_provider == "google" and new.is_admin is False


async def test_a_password_account_converts_and_its_password_stops_working(session_factory, idp):
    await _add_user(session_factory, email="author@example.com")
    async with _client(session_factory) as ac:
        await _session(ac, await _sign_in(ac, idp, "google", _google()))
        refused = await ac.post(
            "/api/auth/login", json={"email": "author@example.com", "password": "old-password-1"}
        )
    assert refused.status_code == 403
    assert "signs in with Google" in refused.json()["detail"]
    converted = await _get(session_factory, "author@example.com")
    assert (converted.auth_provider, converted.external_id) == ("google", "g-1")
    # Destroyed, not just refused: the refusal hides it, and a later change of
    # method must not revive a password the person may have reused elsewhere.
    from app.services.auth import verify_password

    assert not verify_password("old-password-1", converted.hashed_password)


async def test_an_email_the_provider_does_not_vouch_for_converts_nothing(session_factory, idp):
    await _add_user(session_factory, email="author@example.com")
    async with _client(session_factory) as ac:
        resp = await _sign_in(ac, idp, "google", _google(verified=False))
    assert "could not confirm" in _outcome(resp)["sso_error"]
    assert (await _get(session_factory, "author@example.com")).auth_provider == "password"


@pytest.mark.parametrize(
    ("configured", "tid", "trusted"),
    [
        (TENANT, TENANT, True),  # your own directory
        ("common", oidc.PERSONAL_ACCOUNTS_TENANT, True),  # Microsoft verifies these
        ("common", TENANT, False),  # under "common", any directory could be anyone's
        ("common", OTHER_TENANT, False),
        (TENANT, OTHER_TENANT, False),
    ],
)
def test_which_microsoft_emails_are_trusted(configured, tid, trusted):
    """Another directory's administrator can put any address on an account."""
    p = oidc.Provider(**{**MICROSOFT.__dict__, "tenant": configured})
    assert oidc.identity_from_claims(p, _microsoft(tid=tid)).email_trusted is trusted


async def test_an_account_on_one_provider_refuses_the_other(session_factory, idp):
    async with _client(session_factory) as ac:
        await _session(ac, await _sign_in(ac, idp, "google", _google()))
        resp = await _sign_in(ac, idp, "microsoft", _microsoft())
    assert "signs in with Google, not Microsoft" in _outcome(resp)["sso_error"]


async def test_an_unclaimed_account_is_claimed_by_its_first_sign_in(session_factory, idp):
    await _add_user(session_factory, email="admin@example.com", is_admin=True)
    await _add_user(session_factory, email="author@example.com", auth_provider=None)
    async with _client(session_factory) as ac:
        await _session(ac, await _sign_in(ac, idp, "microsoft", _microsoft()))
        other = await _sign_in(ac, idp, "google", _google())
    assert (await _get(session_factory, "author@example.com")).auth_provider == "microsoft"
    assert "signs in with Microsoft" in _outcome(other)["sso_error"]


async def test_an_easy_auth_account_carries_over_to_microsoft(session_factory, idp):
    """Same Entra object ID either way: Brendan's account must keep its works."""
    await _add_user(session_factory, email="author@example.com", auth_provider="external",
                    external_id="oid-1")
    async with _client(session_factory) as ac:
        session = await _session(ac, await _sign_in(ac, idp, "microsoft", _microsoft()))
    assert session["user"]["auth_provider"] == "microsoft"


async def test_a_disabled_account_cannot_sign_in(session_factory, idp):
    await _add_user(session_factory, email="admin@example.com", is_admin=True)
    await _add_user(session_factory, email="author@example.com", is_active=False)
    async with _client(session_factory) as ac:
        resp = await _sign_in(ac, idp, "google", _google())
    assert "disabled" in _outcome(resp)["sso_error"]


async def test_admins_choose_the_method_and_a_password_reset_is_the_way_back(session_factory, idp):
    from app.services.auth import create_access_token

    admin = await _add_user(session_factory, email="admin@example.com", is_admin=True)
    headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    async with _client(session_factory) as ac:
        created = await ac.post("/api/users/", headers=headers, json={
            "email": "author@example.com", "username": "author", "display_name": "Author",
            "sign_in": "google",
        })
        assert created.status_code == 201 and created.json()["auth_provider"] == "google"
        await _session(ac, await _sign_in(ac, idp, "google", _google()))

        uid = created.json()["id"]
        reset = await ac.put(f"/api/users/{uid}/password", headers=headers,
                             json={"password": "new-password-1"})
        assert reset.status_code == 204
        signed_in = await ac.post(
            "/api/auth/login", json={"email": "author@example.com", "password": "new-password-1"}
        )
    assert signed_in.status_code == 200
    restored = await _get(session_factory, "author@example.com")
    assert (restored.auth_provider, restored.external_id) == ("password", None)


async def test_provider_accounts_have_no_password_to_change(session_factory, idp):
    async with _client(session_factory) as ac:
        session = await _session(ac, await _sign_in(ac, idp, "google", _google()))
        resp = await ac.put(
            "/api/auth/me/password",
            headers={"Authorization": f"Bearer {session['token']}"},
            json={"current_password": "anything-1", "new_password": "new-password-1"},
        )
    assert resp.status_code == 400 and "signs in with Google" in resp.json()["detail"]


def test_accounts_rules_know_every_method():
    assert set(accounts.LABELS) == set(accounts.METHODS)
