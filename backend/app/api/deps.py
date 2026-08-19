"""Shared FastAPI dependencies for authentication."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.user import User
from app.services.auth import AUTH_MODE, NO_AUTOLOGIN, decode_access_token, get_or_create_local_user

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """Extract current user from request."""
    if AUTH_MODE == "local" and not NO_AUTOLOGIN:
        return await get_or_create_local_user(db)

    token = _extract_token(request)
    if not token:
        logger.debug("Auth failed: no token in request to %s", request.url.path)
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_access_token(token)
    if not user_id:
        logger.debug("Auth failed: invalid/expired token for %s", request.url.path)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        logger.warning("Auth failed: user %s not found or inactive", user_id)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    logger.debug("Authenticated user %s for %s", user.email, request.url.path)
    return user


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("token")


async def get_optional_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User | None:
    """Like get_current_user but returns None instead of raising."""
    if AUTH_MODE == "local" and not NO_AUTOLOGIN:
        return await get_or_create_local_user(db)

    token = _extract_token(request)
    if not token:
        return None

    user_id = decode_access_token(token)
    if not user_id:
        return None

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user
