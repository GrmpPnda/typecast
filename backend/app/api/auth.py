"""Auth endpoints: login, register, profile."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.user import User
from app.services.auth import (
    AUTH_MODE,
    MIN_PASSWORD_LENGTH,
    NO_AUTOLOGIN,
    OPEN_REGISTRATION,
    count_users,
    create_access_token,
    create_user,
    get_or_create_local_user,
    get_user_by_email,
    set_password,
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
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


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


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class SetupRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class AuthModeResponse(BaseModel):
    mode: str
    open_registration: bool
    setup_required: bool
    # Proxy mode only: where the authenticating proxy signs people in and out.
    login_url: str | None = None
    logout_url: str | None = None


_SSO_ONLY = "Sign-in is handled by single sign-on on this server."


def _refuse_in_proxy_mode() -> None:
    if AUTH_MODE == "proxy":
        raise HTTPException(status_code=400, detail=_SSO_ONLY)


async def _setup_required(db: AsyncSession) -> bool:
    """Whether the deployment has no account yet and needs a first admin.

    Only meaningful in multi-user mode. Local mode creates its single user
    automatically on first use, so there is nothing to set up.
    """
    if AUTH_MODE != "multi":
        return False
    return await count_users(db) == 0


@router.get("/mode", response_model=AuthModeResponse)
async def get_auth_mode(db: AsyncSession = Depends(get_db)):
    effective = "multi" if (NO_AUTOLOGIN and AUTH_MODE == "local") else AUTH_MODE
    setup = await _setup_required(db)
    logger.debug(
        "Auth mode requested: effective=%s (actual=%s, no_autologin=%s, open_reg=%s, setup=%s)",
        effective, AUTH_MODE, NO_AUTOLOGIN, OPEN_REGISTRATION, setup,
    )
    # The frontend uses this on init to pick between the setup page, the login
    # page, and transparent local login.
    response = {
        "mode": effective,
        "open_registration": OPEN_REGISTRATION and AUTH_MODE != "proxy",
        "setup_required": setup,
    }
    if AUTH_MODE == "proxy":
        from app.services import sso

        response["login_url"] = sso.CONFIG.login_url
        response["logout_url"] = sso.CONFIG.logout_url
    return response


@router.post("/setup", response_model=TokenResponse, status_code=201)
async def first_run_setup(data: SetupRequest, db: AsyncSession = Depends(get_db)):
    """Create the first administrator on a deployment that has no accounts.

    Unauthenticated by necessity, so the only thing standing between this and
    an open admin-signup endpoint is the empty-user-table check. It stops
    working permanently the moment any account exists, including one made by
    the TYPECAST_ADMIN_EMAIL bootstrap.
    """
    if AUTH_MODE != "multi":
        logger.debug("Setup refused: auth mode is %s, not multi", AUTH_MODE)
        raise HTTPException(
            status_code=400,
            detail="First-run setup applies to multi-user mode only.",
        )
    if not await _setup_required(db):
        logger.warning("Setup refused for %s: accounts already exist", data.email)
        raise HTTPException(
            status_code=409,
            detail="Setup has already been completed. Sign in instead.",
        )

    try:
        user = await create_user(
            db,
            email=data.email,
            username=data.username,
            display_name=data.display_name,
            password=data.password,
            is_admin=True,
        )
    except (ValueError, IntegrityError) as exc:
        # Two concurrent setup requests can both pass the count check; the
        # unique constraint on email and username settles which one wins.
        await db.rollback()
        logger.warning("Setup failed for %s: %s", data.email, exc)
        raise HTTPException(
            status_code=409, detail="Setup has already been completed. Sign in instead."
        ) from exc

    logger.warning("First-run setup created administrator %s", user.email)
    return {"token": create_access_token(user.id), "user": _user_response(user)}


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    _refuse_in_proxy_mode()
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
    """Self-service signup, off unless TYPECAST_OPEN_REGISTRATION=1.

    Closed by default: on a reachable deployment this endpoint would let anyone
    who finds the URL create an account. Accounts normally come from
    ``/api/users`` instead, which requires an admin.
    """
    _refuse_in_proxy_mode()
    if AUTH_MODE == "local" and not NO_AUTOLOGIN:
        logger.debug("Registration rejected: local mode without no-autologin")
        raise HTTPException(status_code=400, detail="Registration disabled in local mode")
    if not OPEN_REGISTRATION:
        logger.warning("Registration refused for %s: self-service signup is closed", data.email)
        raise HTTPException(
            status_code=403,
            detail="Self-service registration is disabled. Ask an administrator for an account.",
        )

    logger.debug("Registration attempt: email=%s, username=%s", data.email, data.username)
    try:
        user = await create_user(
            db,
            email=data.email,
            username=data.username,
            display_name=data.display_name,
            password=data.password,
        )
    except ValueError as exc:
        logger.info("Registration rejected for %s: %s", data.email, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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


@router.put("/me/password", status_code=204)
async def change_my_password(
    data: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change your own password, proving you know the current one.

    Verifying the current password matters because the token lives in
    localStorage: without it, any XSS that leaks a token could also take over
    the account permanently.
    """
    _refuse_in_proxy_mode()
    if not verify_password(data.current_password, user.hashed_password):
        logger.warning("Password change refused for %s: current password wrong", user.email)
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    try:
        await set_password(db, user, data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
