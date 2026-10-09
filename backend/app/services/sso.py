"""Single sign-on through an authenticating reverse proxy (TYPECAST_AUTH_MODE=proxy).

A proxy in front of the app signs people in and passes who they are in request
headers: Azure App Service and Container Apps "Easy Auth", or oauth2-proxy
anywhere else. Typecast never runs an OAuth flow itself.

Two ways to establish identity, in order of preference:

1. **Verify the identity token** the proxy forwards (``TYPECAST_OIDC_ISSUER`` and
   ``TYPECAST_OIDC_AUDIENCE`` set). The token is signed by the identity provider,
   so a forged request cannot produce one, even one that reaches the container
   without going through the proxy.
2. **Trust the identity headers** (``TYPECAST_PROXY_TRUST_HEADERS=1``). Only safe
   when every request is guaranteed to pass through the proxy, because anyone
   who can reach the app another way can set those headers to anything.

With neither configured, proxy mode refuses to start rather than run unprotected.

Identity becomes an account by ``external_id``, which is the provider's stable
object ID (Entra's ``oid``), never the email, which can change. An account an
administrator created in advance is linked on first sign-in by matching email.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

# Header names and sign-in/out URLs for the proxies we document. Every value
# can be overridden individually with TYPECAST_PROXY_*.
PRESETS: dict[str, dict[str, str]] = {
    # Azure App Service / Container Apps built-in authentication.
    "easyauth": {
        "id_header": "X-MS-CLIENT-PRINCIPAL-ID",
        "name_header": "X-MS-CLIENT-PRINCIPAL-NAME",
        # Requires the token store to be enabled on the Easy Auth configuration.
        "token_header": "X-MS-TOKEN-AAD-ID-TOKEN",
        "login_url": "/.auth/login/aad?post_login_redirect_uri=/",
        "logout_url": "/.auth/logout?post_logout_redirect_uri=/",
    },
    # oauth2-proxy with --pass-user-headers and --pass-authorization-header.
    "oauth2-proxy": {
        "id_header": "X-Forwarded-User",
        "name_header": "X-Forwarded-Email",
        "token_header": "Authorization",
        "login_url": "/oauth2/start?rd=/",
        "logout_url": "/oauth2/sign_out?rd=/",
    },
}

# Easy Auth does not refresh the ID token it forwards, so it expires after about
# an hour while the sign-in session it belongs to lasts hours longer. Checking
# ``exp`` would sign everyone out mid-session. The token's signature, issuer,
# and audience are still verified, and it must have been issued within this
# window, which still rules out forgery entirely and bounds replay of an old one.
DEFAULT_MAX_TOKEN_AGE = 12 * 3600
_CLOCK_SKEW = 300
_JWKS_TTL = 24 * 3600
_JWKS_MIN_REFETCH = 60


class SSOError(Exception):
    """A request that cannot be tied to an account. ``status`` is the HTTP code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class ProxyConfig:
    id_header: str
    name_header: str
    token_header: str
    login_url: str
    logout_url: str
    issuers: list[str] = field(default_factory=list)
    audience: str = ""
    jwks_url: str = ""
    max_token_age: int = DEFAULT_MAX_TOKEN_AGE
    trust_headers: bool = False

    @property
    def verify_tokens(self) -> bool:
        return bool(self.issuers and self.audience)


def load_config(env: Mapping[str, str] | None = None) -> ProxyConfig:
    source = os.environ if env is None else env
    preset_name = source.get("TYPECAST_PROXY_PRESET", "easyauth").strip() or "easyauth"
    if preset_name not in PRESETS:
        raise ValueError(
            f"Unknown TYPECAST_PROXY_PRESET {preset_name!r}; use one of {sorted(PRESETS)}"
        )
    preset = PRESETS[preset_name]

    def pick(key: str) -> str:
        return source.get(f"TYPECAST_PROXY_{key.upper()}", "").strip() or preset[key]

    issuers = [
        i.strip().rstrip("/")
        for i in source.get("TYPECAST_OIDC_ISSUER", "").split(",")
        if i.strip()
    ]
    return ProxyConfig(
        id_header=pick("id_header"),
        name_header=pick("name_header"),
        token_header=pick("token_header"),
        login_url=pick("login_url"),
        logout_url=pick("logout_url"),
        issuers=issuers,
        audience=source.get("TYPECAST_OIDC_AUDIENCE", "").strip(),
        jwks_url=source.get("TYPECAST_OIDC_JWKS_URL", "").strip(),
        max_token_age=int(source.get("TYPECAST_OIDC_MAX_TOKEN_AGE", DEFAULT_MAX_TOKEN_AGE)),
        trust_headers=source.get("TYPECAST_PROXY_TRUST_HEADERS", "0") == "1",
    )


CONFIG = load_config()


def validate_config(config: ProxyConfig | None = None) -> None:
    """Refuse to start proxy mode without a way to tell real users from forgeries."""
    config = config or CONFIG
    if config.verify_tokens:
        insecure = [i for i in config.issuers if not i.startswith("https://")]
        if insecure:
            logger.warning("OIDC issuer is not HTTPS: %s", insecure)
        logger.info(
            "Proxy auth: verifying identity tokens from %s (audience %s)",
            config.issuers, config.audience,
        )
        return
    if config.trust_headers:
        logger.warning(
            "Proxy auth: trusting %s without verifying a token. Anyone who can reach "
            "this server without going through the proxy can sign in as anyone.",
            config.id_header,
        )
        return
    raise RuntimeError(
        "TYPECAST_AUTH_MODE=proxy needs a way to verify who is signing in. Set "
        "TYPECAST_OIDC_ISSUER and TYPECAST_OIDC_AUDIENCE to verify the identity token "
        "the proxy forwards (recommended), or set TYPECAST_PROXY_TRUST_HEADERS=1 if "
        "every request is guaranteed to pass through the proxy."
    )


# --- token verification ------------------------------------------------------------


@dataclass
class _KeyCache:
    keys: dict[str, object] = field(default_factory=dict)
    fetched_at: float = 0.0


_key_cache = _KeyCache()


async def _fetch_jwks(config: ProxyConfig) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=10) as client:
        url = config.jwks_url
        if not url:
            discovery = f"{config.issuers[0]}/.well-known/openid-configuration"
            resp = await client.get(discovery)
            resp.raise_for_status()
            url = resp.json()["jwks_uri"]
        resp = await client.get(url)
        resp.raise_for_status()
        keys = {}
        for jwk in resp.json().get("keys", []):
            if jwk.get("kid") and jwk.get("kty") == "RSA":
                keys[jwk["kid"]] = jwt.PyJWK(jwk, algorithm="RS256").key
    logger.info("Fetched %d signing key(s) from %s", len(keys), url)
    return keys


async def _signing_key(config: ProxyConfig, kid: str):
    now = time.monotonic()
    stale = now - _key_cache.fetched_at > _JWKS_TTL
    unknown = kid not in _key_cache.keys
    # Refetch on an unknown key ID (the provider rotated keys), but not on every
    # request bearing a bogus one.
    if stale or (unknown and now - _key_cache.fetched_at > _JWKS_MIN_REFETCH):
        try:
            _key_cache.keys = await _fetch_jwks(config)
            _key_cache.fetched_at = now
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error("Could not fetch the identity provider's signing keys: %s", exc)
            if not _key_cache.keys:
                raise SSOError(503, "Could not reach the identity provider") from exc
    key = _key_cache.keys.get(kid)
    if key is None:
        raise SSOError(401, "Identity token was not signed by the identity provider")
    return key


async def verify_token(raw: str, config: ProxyConfig | None = None) -> dict:
    config = config or CONFIG
    token = raw.removeprefix("Bearer ").strip()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise SSOError(401, "Identity token is malformed") from exc
    # Pin the algorithm: never let the token choose, which is how "alg: none" and
    # HMAC-with-the-public-key forgeries work.
    if header.get("alg") != "RS256":
        raise SSOError(401, "Identity token uses an unsupported algorithm")

    key = await _signing_key(config, header.get("kid", ""))
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=config.audience,
            options={"verify_exp": False, "verify_iss": False, "require": ["iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Rejected identity token: %s", exc)
        raise SSOError(401, "Identity token is not valid for this application") from exc

    if str(claims.get("iss", "")).rstrip("/") not in config.issuers:
        logger.warning("Rejected identity token from issuer %s", claims.get("iss"))
        raise SSOError(401, "Identity token was issued by an unexpected provider")
    age = time.time() - float(claims["iat"])
    if age > config.max_token_age or age < -_CLOCK_SKEW:
        raise SSOError(401, "Identity token is too old; sign in again")
    return claims


# --- identity ------------------------------------------------------------------------


@dataclass
class Identity:
    external_id: str
    email: str
    name: str


async def identity_from_request(
    headers: Mapping[str, str], config: ProxyConfig | None = None
) -> Identity:
    config = config or CONFIG
    if config.verify_tokens:
        raw = headers.get(config.token_header, "")
        if not raw:
            raise SSOError(401, "Not signed in")
        claims = await verify_token(raw, config)
        # oid is Entra's stable object ID and matches Easy Auth's principal ID
        # header, so switching from trusted headers to verification keeps links.
        external_id = str(claims.get("oid") or claims.get("sub") or "")
        email = str(
            claims.get("preferred_username") or claims.get("email") or claims.get("upn") or ""
        )
        name = str(claims.get("name") or email)
    else:
        external_id = headers.get(config.id_header, "").strip()
        email = headers.get(config.name_header, "").strip()
        name = email
    if not external_id:
        raise SSOError(401, "Not signed in")
    return Identity(external_id=external_id, email=email, name=name or email or external_id)


async def _count_users(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(User))).scalar_one())


async def account_for(db: AsyncSession, identity: Identity) -> User:
    """The account a signed-in identity belongs to, linking or creating as needed."""
    user = (
        await db.execute(select(User).where(User.external_id == identity.external_id))
    ).scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise SSOError(403, "This account has been disabled")
        return user

    # An account an administrator created ahead of time, linked on first sign-in.
    if identity.email:
        candidate = (
            await db.execute(
                select(User).where(func.lower(User.email) == identity.email.lower())
            )
        ).scalar_one_or_none()
        if candidate is not None:
            if candidate.external_id and candidate.external_id != identity.external_id:
                # Someone else already signed in as this account. Linking on email
                # again would hand the account to whoever presents the same name.
                logger.warning(
                    "Refused SSO link for %s: account already linked elsewhere", identity.email
                )
                raise SSOError(403, "This account is linked to a different sign-in")
            if not candidate.is_active:
                raise SSOError(403, "This account has been disabled")
            candidate.external_id = identity.external_id
            await db.commit()
            logger.warning(
                "Linked account %s to SSO identity %s", candidate.email, identity.external_id
            )
            return candidate

    # The first person to sign in to an empty install becomes its administrator,
    # as the first-run setup page does in multi-user mode.
    if await _count_users(db) == 0:
        user = User(
            email=identity.email or f"{identity.external_id}@sso.invalid",
            username=_username_for(identity),
            display_name=identity.name,
            # Unusable: password sign-in is off in proxy mode, and nobody knows it.
            hashed_password=_unusable_password(),
            is_admin=True,
            external_id=identity.external_id,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            # Two first sign-ins at once; the other won. Look again.
            await db.rollback()
            return await account_for(db, identity)
        await db.refresh(user)
        logger.warning("First SSO sign-in created administrator %s", user.email)
        return user

    logger.info("SSO sign-in with no account: %s (%s)", identity.email, identity.external_id)
    who = identity.email or "your sign-in"
    raise SSOError(
        403, f"There is no Typecast account for {who}. Ask an administrator to add you."
    )


def _username_for(identity: Identity) -> str:
    base = (identity.email.split("@")[0] if identity.email else "admin") or "admin"
    return base[:90]


def _unusable_password() -> str:
    from app.services.auth import hash_password

    return hash_password(secrets.token_urlsafe(32))


async def current_user(headers: Mapping[str, str], db: AsyncSession) -> User:
    identity = await identity_from_request(headers)
    return await account_for(db, identity)
