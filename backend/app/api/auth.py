"""Auth endpoints: login, register, profile."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.services.auth import (
    AUTH_MODE,
    NO_AUTOLOGIN,
    create_access_token,
    get_or_create_local_user,
    get_user_by_email,
    get_user_by_username,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    display_name: str
    avatar_url: str | None
    bio: str | None
    is_admin: bool

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


class AuthModeResponse(BaseModel):
    mode: str


@router.get("/mode", response_model=AuthModeResponse)
async def get_auth_mode():
    effective = "multi" if (NO_AUTOLOGIN and AUTH_MODE == "local") else AUTH_MODE
    logger.debug(
        "Auth mode requested: effective=%s (actual=%s, no_autologin=%s)",
        effective, AUTH_MODE, NO_AUTOLOGIN,
    )
    return {"mode": effective}


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    if AUTH_MODE == "local" and not NO_AUTOLOGIN:
        logger.debug("Local auto-login for %s", data.email)
        user = await get_or_create_local_user(db)
        token = create_access_token(user.id)
        return {"token": token, "user": _user_response(user)}

    logger.debug("Login attempt for %s", data.email)
    user = await get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning("Failed login attempt for %s", data.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        logger.warning("Login attempt for disabled account: %s", data.email)
        raise HTTPException(status_code=403, detail="Account is disabled")

    logger.info("User logged in: %s", user.email)
    token = create_access_token(user.id)
    return {"token": token, "user": _user_response(user)}


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if AUTH_MODE == "local" and not NO_AUTOLOGIN:
        logger.debug("Registration rejected: local mode without no-autologin")
        raise HTTPException(status_code=400, detail="Registration disabled in local mode")

    logger.debug("Registration attempt: email=%s, username=%s", data.email, data.username)
    if await get_user_by_email(db, data.email):
        logger.info("Registration rejected: email already registered (%s)", data.email)
        raise HTTPException(status_code=409, detail="Email already registered")
    if await get_user_by_username(db, data.username):
        logger.info("Registration rejected: username taken (%s)", data.username)
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        email=data.email,
        username=data.username,
        display_name=data.display_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered: %s (%s)", user.email, user.username)
    token = create_access_token(user.id)
    return {"token": token, "user": _user_response(user)}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return _user_response(user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.bio is not None:
        user.bio = data.bio
    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


def _user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "is_admin": user.is_admin,
    }
