"""Single sign-on through an authenticating proxy (TYPECAST_AUTH_MODE=proxy).

Real RSA keys and real signed tokens throughout, because the property that
matters is that nothing short of the identity provider's private key produces
a token this app accepts, and a mock of the verifier could not show that.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.main import create_app
from app.models.user import User
from app.models.work import Work
from app.services import sso
from app.services.auth import hash_password

ISSUER = "https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/v2.0"
AUDIENCE = "typecast-client-id"
KID = "test-key-1"


def _keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


PRIVATE_KEY, PUBLIC_KEY = _keypair()
OTHER_PRIVATE, _ = _keypair()


def _token(*, oid=None, email="author@example.com", name="Author", key=PRIVATE_KEY,
           kid=KID, issuer=ISSUER, audience=AUDIENCE, iat=None, exp=None,
           algorithm="RS256", **extra) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer, "aud": audience, "iat": now if iat is None else iat,
        "exp": (now + 3600) if exp is None else exp,
        "oid": oid or str(uuid.uuid4()), "preferred_username": email, "name": name, **extra,
    }
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid})


VERIFYING = sso.ProxyConfig(
    **{k: v for k, v in sso.PRESETS["easyauth"].items()},
    issuers=[ISSUER], audience=AUDIENCE,
)
TRUSTING = sso.ProxyConfig(**sso.PRESETS["easyauth"], trust_headers=True)


@pytest.fixture(autouse=True)
def signing_keys(monkeypatch):
    """The provider's published keys: only PUBLIC_KEY, under KID."""
    sso._key_cache.keys, sso._key_cache.fetched_at = {}, 0.0

    async def fake_fetch(config):
        return {KID: PUBLIC_KEY}

    monkeypatch.setattr(sso, "_fetch_jwks", fake_fetch)
    yield
    sso._key_cache.keys, sso._key_cache.fetched_at = {}, 0.0


def _proxy_mode(monkeypatch, config=VERIFYING):
    for module in ("app.services.auth", "app.api.auth", "app.api.deps"):
        monkeypatch.setattr(f"{module}.AUTH_MODE", "proxy", raising=False)
        monkeypatch.setattr(f"{module}.NO_AUTOLOGIN", False, raising=False)
    monkeypatch.setattr(sso, "CONFIG", config)


def _client(session_factory) -> AsyncClient:
    """The real app with only the database swapped: real authentication."""
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://typecast.example")


def _signed_in(token: str) -> dict:
    return {"X-MS-TOKEN-AAD-ID-TOKEN": token}


# --- configuration -----------------------------------------------------------------


def test_proxy_mode_refuses_to_start_with_no_way_to_verify_identity():
    """Otherwise a forged header is all it takes to be anyone."""
    unprotected = sso.ProxyConfig(**sso.PRESETS["easyauth"])
    with pytest.raises(RuntimeError, match="TYPECAST_OIDC_ISSUER"):
        sso.validate_config(unprotected)
    sso.validate_config(VERIFYING)
    sso.validate_config(TRUSTING)


def test_presets_and_overrides():
    oauth2 = sso.load_config({"TYPECAST_PROXY_PRESET": "oauth2-proxy"})
    assert oauth2.id_header == "X-Forwarded-User"
    assert oauth2.token_header == "Authorization"
    custom = sso.load_config({"TYPECAST_PROXY_ID_HEADER": "X-User-Id",
                              "TYPECAST_OIDC_ISSUER": f"{ISSUER}/, https://sts.windows.net/t/",
                              "TYPECAST_OIDC_AUDIENCE": AUDIENCE})
    assert custom.id_header == "X-User-Id"
    assert custom.issuers == [ISSUER, "https://sts.windows.net/t"], "trailing slashes normalised"
    assert custom.verify_tokens
    with pytest.raises(ValueError, match="Unknown TYPECAST_PROXY_PRESET"):
        sso.load_config({"TYPECAST_PROXY_PRESET": "nope"})


async def test_signing_keys_come_from_oidc_discovery(monkeypatch):
    """Discovery → jwks_uri → keys, the path a real Entra tenant takes."""
    import httpx

    calls = []
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PUBLIC_KEY, as_dict=True)
    jwk.update({"kid": "rotated", "use": "sig"})

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            calls.append(url)
            body = ({"jwks_uri": "https://keys.example/jwks"}
                    if url.endswith("openid-configuration") else {"keys": [jwk]})
            return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(sso.httpx, "AsyncClient", FakeClient)
    monkeypatch.undo()  # drop the autouse fake fetch for this test only
    monkeypatch.setattr(sso.httpx, "AsyncClient", FakeClient)
    keys = await sso._fetch_jwks(VERIFYING)
    assert calls == [f"{ISSUER}/.well-known/openid-configuration", "https://keys.example/jwks"]
    assert set(keys) == {"rotated"}


# --- token verification --------------------------------------------------------------


async def test_a_valid_token_is_accepted():
    claims = await sso.verify_token(_token(oid="abc"), VERIFYING)
    assert claims["oid"] == "abc"


async def test_the_bearer_prefix_is_accepted():
    """oauth2-proxy forwards the token as Authorization: Bearer <token>."""
    await sso.verify_token("Bearer " + _token(), VERIFYING)


@pytest.mark.parametrize(
    ("label", "token"),
    [
        ("signed with a different key", lambda: _token(key=OTHER_PRIVATE)),
        ("for a different application", lambda: _token(audience="someone-else")),
        ("from a different tenant", lambda: _token(issuer="https://login.microsoftonline.com/evil/v2.0")),
        ("issued too long ago", lambda: _token(iat=int(time.time()) - 13 * 3600)),
        ("issued in the future", lambda: _token(iat=int(time.time()) + 3600)),
        ("with an unknown key ID", lambda: _token(kid="not-ours")),
        ("unsigned (alg none)", lambda: jwt.encode({"iss": ISSUER, "aud": AUDIENCE,
                                                    "iat": int(time.time()), "oid": "x"},
                                                   None, algorithm="none",
                                                   headers={"kid": KID})),
        ("HMAC-signed", lambda: jwt.encode({"iss": ISSUER, "aud": AUDIENCE,
                                            "iat": int(time.time()), "oid": "x"},
                                           "a-shared-secret-of-sufficient-length-1234",
                                           algorithm="HS256", headers={"kid": KID})),
        ("garbage", lambda: "not.a.token"),
    ],
)
async def test_forged_or_foreign_tokens_are_rejected(label, token):
    with pytest.raises(sso.SSOError) as exc:
        await sso.verify_token(token(), VERIFYING)
    assert exc.value.status == 401, label


async def test_an_expired_token_within_the_session_window_is_accepted():
    """Easy Auth does not refresh the ID token it forwards; checking exp would sign
    everyone out an hour into a sign-in session that lasts much longer."""
    old_but_recent = int(time.time()) - 2 * 3600
    await sso.verify_token(_token(iat=old_but_recent, exp=old_but_recent + 3600), VERIFYING)


async def test_spoofed_identity_headers_are_ignored_when_verifying():
    """The headers are exactly what an attacker bypassing the proxy would send."""
    with pytest.raises(sso.SSOError) as exc:
        await sso.identity_from_request(
            {"X-MS-CLIENT-PRINCIPAL-ID": "victim-oid", "X-MS-CLIENT-PRINCIPAL-NAME": "victim@x"},
            VERIFYING,
        )
    assert exc.value.status == 401


async def test_trusted_header_mode_reads_the_headers():
    identity = await sso.identity_from_request(
        {"X-MS-CLIENT-PRINCIPAL-ID": "oid-1", "X-MS-CLIENT-PRINCIPAL-NAME": "a@b.example"},
        TRUSTING,
    )
    assert (identity.external_id, identity.email) == ("oid-1", "a@b.example")


# --- accounts ------------------------------------------------------------------------


def _identity(oid="oid-1", email="author@example.com"):
    return sso.Identity(external_id=oid, email=email, name="Author")


async def test_the_first_sign_in_to_an_empty_install_becomes_the_administrator(db_session):
    user = await sso.account_for(db_session, _identity())
    assert user.is_admin and user.external_id == "oid-1"


async def test_strangers_are_turned_away_once_an_install_has_accounts(db_session):
    await sso.account_for(db_session, _identity())
    with pytest.raises(sso.SSOError) as exc:
        await sso.account_for(db_session, _identity("oid-2", "stranger@example.com"))
    assert exc.value.status == 403
    assert "Ask an administrator" in str(exc.value)


async def test_a_precreated_account_links_on_first_sign_in(db_session):
    db_session.add(User(email="Reader@Example.com", username="reader", display_name="R",
                        hashed_password=hash_password("x" * 12)))
    await db_session.commit()

    linked = await sso.account_for(db_session, _identity("oid-r", "reader@example.com"))
    assert linked.username == "reader" and linked.external_id == "oid-r"

    # Later the UPN changes; the object ID does not, and that is what is matched.
    again = await sso.account_for(db_session, _identity("oid-r", "reader.renamed@example.com"))
    assert again.id == linked.id


async def test_a_linked_account_cannot_be_claimed_by_another_identity(db_session):
    """Matching on email a second time would hand the account to anyone presenting it."""
    await sso.account_for(db_session, _identity("oid-owner", "owner@example.com"))
    with pytest.raises(sso.SSOError) as exc:
        await sso.account_for(db_session, _identity("oid-impostor", "owner@example.com"))
    assert exc.value.status == 403
    assert "different sign-in" in str(exc.value)


async def test_a_disabled_account_is_refused(db_session):
    user = await sso.account_for(db_session, _identity())
    user.is_active = False
    await db_session.commit()
    with pytest.raises(sso.SSOError) as exc:
        await sso.account_for(db_session, _identity())
    assert exc.value.status == 403


async def test_the_env_bootstrap_names_the_administrator_in_proxy_mode(
    db_session, monkeypatch
):
    """No password needed, and it beats "first person to sign in wins"."""
    from app.services.auth import ensure_admin_user

    monkeypatch.setattr("app.services.auth.AUTH_MODE", "proxy")
    monkeypatch.setenv("TYPECAST_ADMIN_EMAIL", "boss@example.com")
    monkeypatch.delenv("TYPECAST_ADMIN_PASSWORD", raising=False)
    await ensure_admin_user(db_session)

    with pytest.raises(sso.SSOError):
        await sso.account_for(db_session, _identity("oid-early", "early@example.com"))
    boss = await sso.account_for(db_session, _identity("oid-boss", "boss@example.com"))
    assert boss.is_admin and boss.external_id == "oid-boss"


# --- the whole app in proxy mode -----------------------------------------------------


async def test_end_to_end_sign_in_and_isolation(session_factory, monkeypatch):
    _proxy_mode(monkeypatch)
    alice_token = _token(oid="alice", email="alice@example.com")
    bob_token = _token(oid="bob", email="bob@example.com")

    async with _client(session_factory) as ac:
        # Alice is first in, so she becomes the administrator and adds Bob.
        me = await ac.get("/api/auth/me", headers=_signed_in(alice_token))
        assert me.status_code == 200 and me.json()["is_admin"] is True
        created = await ac.post(
            "/api/users/", headers=_signed_in(alice_token),
            json={"email": "bob@example.com", "username": "bob", "display_name": "Bob"},
        )
        assert created.status_code == 201, "SSO accounts need no password"
        assert created.json()["sso_linked"] is False

        work = await ac.post("/api/works/", headers=_signed_in(alice_token),
                             json={"title": "Alice's", "author": "A"})
        assert work.status_code == 201
        work_id = work.json()["id"]

        # Bob signs in, links to the account Alice made, and sees none of her work.
        assert (await ac.get("/api/auth/me", headers=_signed_in(bob_token))).status_code == 200
        assert (await ac.get("/api/works/", headers=_signed_in(bob_token))).json() == []
        stolen = await ac.get(f"/api/works/{work_id}", headers=_signed_in(bob_token))
        assert stolen.status_code == 404
        users = await ac.get("/api/users/", headers=_signed_in(alice_token))
        assert {u["email"]: u["sso_linked"] for u in users.json()}["bob@example.com"] is True


async def test_password_flows_are_switched_off(session_factory, monkeypatch):
    _proxy_mode(monkeypatch)
    token = _token()
    async with _client(session_factory) as ac:
        uid = (await ac.get("/api/auth/me", headers=_signed_in(token))).json()["id"]
        for method, path, body in [
            ("post", "/api/auth/login", {"email": "a@b.c", "password": "whatever-123"}),
            ("post", "/api/auth/register", {"email": "new@b.c", "username": "new",
                                            "display_name": "N", "password": "whatever-123"}),
            ("put", "/api/auth/me/password", {"current_password": "x", "new_password": "y" * 9}),
            ("put", f"/api/users/{uid}/password", {"password": "y" * 9}),
        ]:
            resp = await getattr(ac, method)(path, json=body, headers=_signed_in(token))
            assert resp.status_code == 400, f"{path} returned {resp.status_code}"


async def test_auth_mode_tells_the_frontend_where_to_sign_in_and_out(session_factory, monkeypatch):
    _proxy_mode(monkeypatch)
    async with _client(session_factory) as ac:
        body = (await ac.get("/api/auth/mode")).json()
    assert body["mode"] == "proxy"
    assert body["setup_required"] is False
    assert body["login_url"].startswith("/.auth/login/aad")
    assert body["logout_url"].startswith("/.auth/logout")


async def test_no_token_means_no_access_anywhere(session_factory, monkeypatch):
    """The full route table, through the real proxy-mode authentication."""
    import re

    from tests.test_authorization import PUBLIC, ROUTES

    _proxy_mode(monkeypatch)
    spoof = {"X-MS-CLIENT-PRINCIPAL-ID": "victim", "X-MS-CLIENT-PRINCIPAL-NAME": "victim@x"}
    async with _client(session_factory) as ac:
        for method, path, _ in ROUTES:
            if (method, path) in PUBLIC:
                continue
            url = re.sub(r"\{\w+\}", str(uuid.uuid4()), path)
            resp = await ac.request(method, url, headers=spoof)
            assert resp.status_code == 401, f"{method} {path}: {resp.status_code}"


async def test_trusted_header_mode_end_to_end(session_factory, monkeypatch):
    _proxy_mode(monkeypatch, TRUSTING)
    headers = {"X-MS-CLIENT-PRINCIPAL-ID": "oid-h", "X-MS-CLIENT-PRINCIPAL-NAME": "h@example.com"}
    async with _client(session_factory) as ac:
        me = await ac.get("/api/auth/me", headers=headers)
        assert me.status_code == 200 and me.json()["email"] == "h@example.com"
        assert (await ac.get("/api/works/")).status_code == 401

    async with session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        works = (await session.execute(select(Work))).scalars().all()
    assert [u.external_id for u in users] == ["oid-h"] and works == []
