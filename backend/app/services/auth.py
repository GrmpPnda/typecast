"""Authentication service: password hashing, JWT tokens, user lookup."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from base64 import b64decode, b64encode
from json import dumps, loads

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_SECONDS = int(os.environ.get("TYPECAST_TOKEN_EXPIRY", "86400"))
# Carries a session token for reading /uploads, where an <img> cannot send a
# header. Scoped to that path and honoured only for reads there (see deps.py).
UPLOADS_COOKIE = "typecast_uploads"
AUTH_MODE = os.environ.get("TYPECAST_AUTH_MODE", "local")
NO_AUTOLOGIN = os.environ.get("TYPECAST_NO_AUTOLOGIN", "0") == "1"

# Self-service signup is off unless explicitly enabled. An internet-reachable
# deployment with open registration lets anyone who finds the URL create an
# account, so accounts are created by an admin instead.
OPEN_REGISTRATION = os.environ.get("TYPECAST_OPEN_REGISTRATION", "0") == "1"

MIN_PASSWORD_LENGTH = 8

logger.info(
    "Auth config: mode=%s, no_autologin=%s, open_registration=%s, token_expiry=%ds",
    AUTH_MODE, NO_AUTOLOGIN, OPEN_REGISTRATION, TOKEN_EXPIRY_SECONDS,
)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260000)
    return b64encode(salt + key).decode()


def verify_password(password: str, hashed: str) -> bool:
    raw = b64decode(hashed.encode())
    salt, stored_key = raw[:16], raw[16:]
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=260000)
    return hmac.compare_digest(key, stored_key)


def _sign(data: str) -> str:
    return hmac.HMAC(
        settings.SECRET_KEY.encode(), data.encode(), hashlib.sha256
    ).hexdigest()


def create_access_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
    }
    payload_b64 = b64encode(dumps(payload).encode()).decode()
    sig = _sign(payload_b64)
    logger.debug("Created access token for user %s", user_id)
    return f"{payload_b64}.{sig}"


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            logger.debug("Token decode failed: malformed token (no separator)")
            return None
        payload_b64, sig = parts
        if not hmac.compare_digest(_sign(payload_b64), sig):
            logger.debug("Token decode failed: invalid signature")
            return None
        payload = loads(b64decode(payload_b64).decode())
        if payload.get("exp", 0) < time.time():
            logger.debug("Token decode failed: expired (exp=%s)", payload.get("exp"))
            return None
        return uuid.UUID(payload["sub"])
    except Exception:
        logger.debug("Token decode failed: exception during parsing", exc_info=True)
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    logger.debug("Looking up user by email: %s", email)
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    logger.debug("Looking up user by username: %s", username)
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    username: str,
    display_name: str,
    password: str,
    is_admin: bool = False,
) -> User:
    """Insert a user, rejecting a duplicate email or username.

    Raises ``ValueError`` on conflict or a too-short password so both the admin
    endpoint and the startup bootstrap enforce the same rules.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if await get_user_by_email(db, email):
        raise ValueError("Email already registered")
    if await get_user_by_username(db, username):
        raise ValueError("Username already taken")

    user = User(
        email=email,
        username=username,
        display_name=display_name,
        hashed_password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Created user %s (admin=%s)", user.email, is_admin)
    return user


async def set_password(db: AsyncSession, user: User, password: str) -> None:
    """Replace a user's password hash.

    Re-fetches the row through ``db`` before writing. Mutating the passed
    instance directly is a silent no-op when it belongs to a different session,
    which is easy to do because the caller usually got it from a dependency.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    hashed = hash_password(password)
    target = await db.get(User, user.id)
    if target is None:
        raise ValueError("User no longer exists")
    target.hashed_password = hashed
    await db.commit()
    user.hashed_password = hashed  # keep the caller's copy consistent
    logger.info("Password changed for %s", target.email)


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


async def ensure_admin_user(db: AsyncSession) -> None:
    """Create the first admin from the environment, if there are no users yet.

    Needed because registration is admin-only: a fresh deployment would
    otherwise have no account able to create the first one. Deliberately does
    nothing once any user exists, so the variables cannot silently reset a
    password or resurrect a deleted account.
    """
    email = os.environ.get("TYPECAST_ADMIN_EMAIL", "").strip()
    password = os.environ.get("TYPECAST_ADMIN_PASSWORD", "")
    if AUTH_MODE == "proxy" and email:
        # Single sign-on: the account links to this person's identity the first
        # time they sign in, so it needs no usable password. Naming the admin up
        # front also beats "first person to sign in becomes the administrator".
        password = secrets.token_urlsafe(32)
    if not email or not password:
        return

    existing = await count_users(db)
    if existing:
        logger.debug("Admin bootstrap skipped: %d user(s) already exist", existing)
        return

    try:
        await create_user(
            db,
            email=email,
            username=os.environ.get("TYPECAST_ADMIN_USERNAME", "admin").strip() or "admin",
            display_name=os.environ.get("TYPECAST_ADMIN_NAME", "Administrator").strip()
            or "Administrator",
            password=password,
            is_admin=True,
        )
        logger.warning("Bootstrapped first admin account: %s", email)
    except ValueError as exc:
        logger.error("Admin bootstrap failed: %s", exc)


LOCAL_DEFAULT_PASSWORD = "typecast"


async def get_or_create_local_user(db: AsyncSession) -> User:
    """Get or create the default local user for single-user mode."""
    result = await db.execute(select(User).where(User.email == "local@typecast.local"))
    user = result.scalar_one_or_none()
    if user:
        if NO_AUTOLOGIN and not verify_password(LOCAL_DEFAULT_PASSWORD, user.hashed_password):
            logger.info("Resetting local user password for no-autologin mode")
            user.hashed_password = hash_password(LOCAL_DEFAULT_PASSWORD)
            await db.commit()
        return user

    logger.info("Creating default local user")
    user = User(
        email="local@typecast.local",
        username="author",
        display_name="Author",
        hashed_password=hash_password(LOCAL_DEFAULT_PASSWORD),
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
