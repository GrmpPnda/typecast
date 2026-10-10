"""Signing in with Microsoft or Google, run by Typecast itself (OpenID Connect).

The authorization-code flow with PKCE, a nonce, and a state value bound to the
browser by a cookie:

1. ``start`` remembers a fresh state, nonce, and PKCE verifier, sets the state in
   a short-lived cookie, and sends the browser to the provider.
2. The provider sends the browser back to ``callback`` with a code and the state.
   The state must match both a pending sign-in and the browser's cookie, so a
   callback link crafted by someone else cannot sign this browser in to their
   account. Each state works once.
3. The code is exchanged for an ID token directly with the provider, using the
   client secret and the PKCE verifier. The token's signature, issuer,
   audience, expiry, and nonce are all checked.
4. The account rules in ``app.services.accounts`` decide which account it is.
   The browser gets a single-use code, never a token in a URL, and trades it for
   a session.

Configured per provider from the environment; a provider with no client ID is
simply not offered.

* ``TYPECAST_MICROSOFT_CLIENT_ID``, ``_CLIENT_SECRET``, ``_TENANT`` (a directory
  ID, or ``common``, ``organizations``, or ``consumers``; default ``common``)
* ``TYPECAST_GOOGLE_CLIENT_ID``, ``_CLIENT_SECRET``
* ``TYPECAST_PUBLIC_URL``: the address the app is reached at, to build redirect
  URIs from. Unset, they come from the request.
* ``TYPECAST_MICROSOFT_DISCOVERY_URL`` / ``TYPECAST_GOOGLE_DISCOVERY_URL``: where
  to fetch the provider's OpenID configuration, for testing against a stand-in
  provider. Unset, the real provider's.

Pending sign-ins live in memory, which matches the deployment of one replica. A
restart in the middle of a sign-in means signing in again.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
import jwt

from app.services import accounts

logger = logging.getLogger(__name__)

# Microsoft's tenant for personal accounts (outlook.com and the like). Microsoft
# verifies those addresses itself, so their email can be trusted.
PERSONAL_ACCOUNTS_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
_MULTI_TENANT = {"common", "organizations", "consumers"}

PENDING_TTL = 10 * 60
CODE_TTL = 60
_MAX_PENDING = 1000
_DISCOVERY_TTL = 24 * 3600
_JWKS_MIN_REFETCH = 60
_CLOCK_SKEW = 300

STATE_COOKIE = "typecast_oidc_state"
COOKIE_PATH = "/api/auth/oidc"


class OIDCError(Exception):
    """Shown to the person signing in. ``status`` is the HTTP code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    client_id: str
    client_secret: str
    discovery_url: str
    tenant: str = ""


def load_providers(env: Mapping[str, str] | None = None) -> dict[str, Provider]:
    source = os.environ if env is None else env
    found: dict[str, Provider] = {}
    ms_id = source.get("TYPECAST_MICROSOFT_CLIENT_ID", "").strip()
    if ms_id:
        tenant = source.get("TYPECAST_MICROSOFT_TENANT", "").strip() or "common"
        found[accounts.MICROSOFT] = Provider(
            id=accounts.MICROSOFT,
            name="Microsoft",
            client_id=ms_id,
            client_secret=source.get("TYPECAST_MICROSOFT_CLIENT_SECRET", ""),
            discovery_url=source.get("TYPECAST_MICROSOFT_DISCOVERY_URL", "").strip() or (
                f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
            ),
            tenant=tenant,
        )
    google_id = source.get("TYPECAST_GOOGLE_CLIENT_ID", "").strip()
    if google_id:
        found[accounts.GOOGLE] = Provider(
            id=accounts.GOOGLE,
            name="Google",
            client_id=google_id,
            client_secret=source.get("TYPECAST_GOOGLE_CLIENT_SECRET", ""),
            discovery_url=source.get("TYPECAST_GOOGLE_DISCOVERY_URL", "").strip()
            or "https://accounts.google.com/.well-known/openid-configuration",
        )
    for provider in found.values():
        if not provider.client_secret:
            logger.error("%s sign-in has a client ID but no client secret", provider.name)
    logger.info("Sign-in providers configured: %s", sorted(found) or "none")
    return found


PROVIDERS = load_providers()
PUBLIC_URL = os.environ.get("TYPECAST_PUBLIC_URL", "").strip().rstrip("/")


def provider(provider_id: str) -> Provider:
    found = PROVIDERS.get(provider_id)
    if found is None:
        raise OIDCError(404, "That sign-in method is not available on this server.")
    return found


def redirect_uri(base_url: str, provider_id: str) -> str:
    base = PUBLIC_URL or base_url.rstrip("/")
    return f"{base}{COOKIE_PATH}/{provider_id}/callback"


# --- provider metadata and keys --------------------------------------------------


@dataclass
class _Metadata:
    document: dict = field(default_factory=dict)
    keys: dict[str, object] = field(default_factory=dict)
    fetched_at: float = 0.0
    keys_fetched_at: float = 0.0


_metadata: dict[str, _Metadata] = {}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10)


async def _discovery(p: Provider) -> dict:
    meta = _metadata.setdefault(p.id, _Metadata())
    if meta.document and time.monotonic() - meta.fetched_at < _DISCOVERY_TTL:
        return meta.document
    try:
        async with _client() as client:
            resp = await client.get(p.discovery_url)
            resp.raise_for_status()
            meta.document = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Could not fetch %s's OpenID configuration: %s", p.name, exc)
        if not meta.document:
            raise OIDCError(503, f"Could not reach {p.name}. Try again shortly.") from exc
        return meta.document
    meta.fetched_at = time.monotonic()
    logger.info("Fetched %s's OpenID configuration", p.name)
    return meta.document


async def _signing_key(p: Provider, kid: str):
    meta = _metadata.setdefault(p.id, _Metadata())
    now = time.monotonic()
    stale = now - meta.keys_fetched_at > _DISCOVERY_TTL
    unknown = kid not in meta.keys
    if stale or (unknown and now - meta.keys_fetched_at > _JWKS_MIN_REFETCH):
        document = await _discovery(p)
        try:
            async with _client() as client:
                resp = await client.get(document["jwks_uri"])
                resp.raise_for_status()
                meta.keys = {
                    jwk["kid"]: jwt.PyJWK(jwk, algorithm="RS256").key
                    for jwk in resp.json().get("keys", [])
                    if jwk.get("kid") and jwk.get("kty") == "RSA"
                }
            meta.keys_fetched_at = now
            logger.info("Fetched %d signing key(s) for %s", len(meta.keys), p.name)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error("Could not fetch %s's signing keys: %s", p.name, exc)
            if not meta.keys:
                raise OIDCError(503, f"Could not reach {p.name}. Try again shortly.") from exc
    key = meta.keys.get(kid)
    if key is None:
        raise OIDCError(401, f"The sign-in was not signed by {p.name}.")
    return key


# --- pending sign-ins and single-use codes ----------------------------------------


@dataclass
class _Pending:
    provider: str
    nonce: str
    verifier: str
    redirect_uri: str
    created: float


_pending: dict[str, _Pending] = {}
_codes: dict[str, tuple[uuid.UUID, float]] = {}


def _prune(now: float) -> None:
    for state in [s for s, p in _pending.items() if now - p.created > PENDING_TTL]:
        del _pending[state]
    for code in [c for c, (_, t) in _codes.items() if now - t > CODE_TTL]:
        del _codes[code]
    while len(_pending) > _MAX_PENDING:
        _pending.pop(next(iter(_pending)))


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def begin(provider_id: str, base_url: str) -> tuple[str, str]:
    """Start a sign-in. Returns (state, URL to send the browser to)."""
    p = provider(provider_id)
    document = await _discovery(p)
    now = time.monotonic()
    _prune(now)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    uri = redirect_uri(base_url, p.id)
    _pending[state] = _Pending(p.id, nonce, verifier, uri, now)
    params = {
        "client_id": p.client_id,
        "response_type": "code",
        "redirect_uri": uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        # Always show the account picker, so switching accounts is possible.
        "prompt": "select_account",
    }
    logger.info("Starting %s sign-in (redirect %s)", p.name, uri)
    return state, f"{document['authorization_endpoint']}?{urlencode(params)}"


def take_pending(provider_id: str, state: str, cookie_state: str | None) -> _Pending:
    """The pending sign-in for this callback, consumed. Raises if it is not this browser's."""
    _prune(time.monotonic())
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        logger.warning("Refused %s callback: state does not match this browser", provider_id)
        raise OIDCError(400, "This sign-in was not started in this browser. Try again.")
    pending = _pending.pop(state, None)
    if pending is None or pending.provider != provider_id:
        logger.warning("Refused %s callback: unknown or expired state", provider_id)
        raise OIDCError(400, "This sign-in has expired or was already used. Try again.")
    return pending


async def identity_from_code(provider_id: str, code: str, pending: _Pending) -> accounts.Identity:
    p = provider(provider_id)
    document = await _discovery(p)
    try:
        async with _client() as client:
            resp = await client.post(
                document["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": pending.redirect_uri,
                    "client_id": p.client_id,
                    "client_secret": p.client_secret,
                    "code_verifier": pending.verifier,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.error("Could not reach %s's token endpoint: %s", p.name, exc)
        raise OIDCError(503, f"Could not reach {p.name}. Try again shortly.") from exc
    is_json = resp.headers.get("content-type", "").startswith("application/json")
    body = resp.json() if is_json else {}
    if resp.status_code != 200 or "id_token" not in body:
        logger.error(
            "%s refused the code exchange (%s): %s",
            p.name, resp.status_code, body.get("error_description") or body.get("error"),
        )
        raise OIDCError(401, f"{p.name} did not complete the sign-in. Try again.")
    claims = await verify_id_token(p, body["id_token"], pending.nonce)
    return identity_from_claims(p, claims)


async def verify_id_token(p: Provider, raw: str, nonce: str) -> dict:
    try:
        header = jwt.get_unverified_header(raw)
    except jwt.PyJWTError as exc:
        raise OIDCError(401, f"{p.name} returned a malformed sign-in.") from exc
    if header.get("alg") != "RS256":
        raise OIDCError(401, f"{p.name} returned a sign-in with an unsupported algorithm.")
    key = await _signing_key(p, header.get("kid", ""))
    try:
        claims = jwt.decode(
            raw, key, algorithms=["RS256"], audience=p.client_id, leeway=_CLOCK_SKEW,
            options={"verify_iss": False, "require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Rejected %s ID token: %s", p.name, exc)
        raise OIDCError(401, f"{p.name}'s sign-in is not valid for this application.") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        logger.warning("Rejected %s ID token: nonce mismatch", p.name)
        raise OIDCError(401, "This sign-in was replayed or not started here. Try again.")
    _check_issuer(p, claims)
    return claims


def _check_issuer(p: Provider, claims: dict) -> None:
    issuer = str(claims.get("iss", "")).rstrip("/")
    if p.id == accounts.GOOGLE:
        ok = issuer in ("https://accounts.google.com", "accounts.google.com")
    else:
        tid = str(claims.get("tid", ""))
        ok = bool(tid) and issuer == f"https://login.microsoftonline.com/{tid}/v2.0"
        if ok and p.tenant not in _MULTI_TENANT:
            ok = tid.lower() == p.tenant.lower()
        if ok and p.tenant == "consumers":
            ok = tid == PERSONAL_ACCOUNTS_TENANT
    if not ok:
        logger.warning("Rejected %s ID token from issuer %s", p.name, issuer)
        raise OIDCError(401, "That sign-in came from outside what this server accepts.")


def identity_from_claims(p: Provider, claims: dict) -> accounts.Identity:
    name = str(claims.get("name") or "")
    if p.id == accounts.GOOGLE:
        email = str(claims.get("email") or "")
        return accounts.Identity(
            provider=p.id, subject=str(claims["sub"]), email=email, name=name or email,
            email_trusted=bool(email) and claims.get("email_verified") is True,
        )
    # Microsoft: oid is stable for the person across every app in the directory,
    # and matches the ID Easy Auth used, so earlier links carry over.
    tid = str(claims.get("tid", ""))
    email = str(claims.get("email") or claims.get("preferred_username") or "")
    own_directory = p.tenant not in _MULTI_TENANT and tid.lower() == p.tenant.lower()
    return accounts.Identity(
        provider=p.id, subject=str(claims.get("oid") or claims["sub"]),
        email=email, name=name or email,
        # Another directory's administrator can put any address on an account,
        # so only your own directory's and Microsoft's personal accounts count.
        email_trusted=bool(email) and (own_directory or tid == PERSONAL_ACCOUNTS_TENANT),
    )


def issue_code(user_id: uuid.UUID) -> str:
    now = time.monotonic()
    _prune(now)
    code = secrets.token_urlsafe(32)
    _codes[code] = (user_id, now)
    return code


def redeem_code(code: str) -> uuid.UUID:
    _prune(time.monotonic())
    entry = _codes.pop(code, None)
    if entry is None:
        raise OIDCError(400, "This sign-in link has expired or was already used. Sign in again.")
    return entry[0]


def reset() -> None:
    """For tests: forget every pending sign-in, code, and cached document."""
    _pending.clear()
    _codes.clear()
    _metadata.clear()
