"""Authentication service: password hashing, JWT tokens, user lookup."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from base64 import b64decode, b64encode
from json import dumps, loads

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_SECONDS = int(os.environ.get("TYPECAST_TOKEN_EXPIRY", "86400"))
AUTH_MODE = os.environ.get("TYPECAST_AUTH_MODE", "local")
NO_AUTOLOGIN = os.environ.get("TYPECAST_NO_AUTOLOGIN", "0") == "1"

logger.info(
    "Auth config: mode=%s, no_autologin=%s, token_expiry=%ds",
    AUTH_MODE, NO_AUTOLOGIN, TOKEN_EXPIRY_SECONDS,
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
