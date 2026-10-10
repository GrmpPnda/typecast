"""Admin user management.

Registration is admin-only (see ``TYPECAST_OPEN_REGISTRATION``), so these
endpoints are the only way accounts come into existence on a deployment after
the startup bootstrap creates the first admin.

Two guards are load-bearing and both exist to stop an admin locking everyone
out: the last remaining admin cannot be demoted or deactivated, and nobody can
delete or deactivate their own account.
"""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.engine import get_db
from app.models.user import User
from app.services.auth import MIN_PASSWORD_LENGTH, create_user, set_password

logger = logging.getLogger(__name__)
router = APIRouter()


class AdminUserResponse(BaseModel):
    id: str
    email: str
    username: str
    display_name: str
    is_active: bool
    is_admin: bool
    # Single sign-on: whether this person has signed in yet. An unlinked account
    # links on their first sign-in by matching email.
    sso_linked: bool = False
    # How the account signs in; None means its first single sign-on decides.
    auth_provider: str | None = None


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    # Required for password accounts. Under single sign-on there is none to set:
    # the account links to the person's identity on their first sign-in.
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH)
    is_admin: bool = False
    # "password", "microsoft", "google", or "any" (whichever provider they sign
    # in with first). Ignored under proxy sign-in, where it is always the proxy.
    sign_in: str = "password"


class UserPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    is_admin: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


def _response(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "sso_linked": user.external_id is not None,
        "auth_provider": user.auth_provider,
    }


async def _count_other_active_admins(db: AsyncSession, exclude: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.is_admin.is_(True), User.is_active.is_(True), User.id != exclude)
    )
    return int(result.scalar_one())


async def _load(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if not user:
        logger.info("User management: %s not found", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/", response_model=list[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Every account, oldest first."""
    result = await db.execute(select(User).order_by(User.created_at))
    users = list(result.scalars().all())
    logger.debug("Listed %d users", len(users))
    return [_response(u) for u in users]


@router.post("/", response_model=AdminUserResponse, status_code=201)
async def create_account(
    data: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.services import accounts
    from app.services import auth as auth_service

    password = data.password
    method: str | None = data.sign_in
    if auth_service.AUTH_MODE == "proxy":
        password, method = secrets.token_urlsafe(32), accounts.EXTERNAL
    elif method == accounts.PASSWORD:
        if not password:
            raise HTTPException(status_code=422, detail="A password is required")
    elif method in (*accounts.PROVIDERS, "any"):
        # No password: they sign in with the provider, which binds the account.
        password, method = secrets.token_urlsafe(32), (None if method == "any" else method)
    else:
        raise HTTPException(status_code=422, detail=f"Unknown sign-in method {method!r}")
    try:
        user = await create_user(
            db,
            email=data.email,
            username=data.username,
            display_name=data.display_name,
            password=password,
            is_admin=data.is_admin,
        )
    except ValueError as exc:
        logger.info("User creation rejected: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if user.auth_provider != method:
        user.auth_provider = method
        await db.commit()
    logger.info("%s created account %s (sign-in: %s)", admin.email, user.email, method or "any")
    return _response(user)


@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_account(
    user_id: uuid.UUID,
    data: UserPatchRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await _load(db, user_id)

    # Refuse any change that would leave the deployment with no way in.
    removes_admin_access = (data.is_admin is False and user.is_admin) or (
        data.is_active is False and user.is_admin and user.is_active
    )
    if removes_admin_access and await _count_other_active_admins(db, user.id) == 0:
        logger.warning("Refused change leaving no active admin (target=%s)", user.email)
        raise HTTPException(
            status_code=409, detail="Cannot remove the last active administrator"
        )
    if data.is_active is False and user.id == admin.id:
        raise HTTPException(status_code=409, detail="Cannot deactivate your own account")

    if data.display_name is not None:
        user.display_name = data.display_name
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_admin is not None:
        user.is_admin = data.is_admin

    await db.commit()
    await db.refresh(user)
    logger.info(
        "%s updated %s (active=%s, admin=%s)",
        admin.email, user.email, user.is_active, user.is_admin,
    )
    return _response(user)


@router.put("/{user_id}/password", status_code=204)
async def reset_account_password(
    user_id: uuid.UUID,
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Set another account's password. There is no email reset flow."""
    from app.services import auth as auth_service

    if auth_service.AUTH_MODE == "proxy":
        raise HTTPException(
            status_code=400, detail="Passwords are managed by single sign-on on this server."
        )
    user = await _load(db, user_id)
    try:
        # Also the recovery path for an account whose Google or Microsoft sign-in
        # was lost: it becomes a password account.
        await set_password(db, user, data.password, switch_to_password=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.warning("%s reset the password for %s", admin.email, user.email)


async def _owned_content_counts(db: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """How much content a delete would cascade away."""
    from app.models.conversation import Conversation
    from app.models.series import Series
    from app.models.work import Work

    counts = {}
    for label, model in (("works", Work), ("series", Series), ("conversations", Conversation)):
        result = await db.execute(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )
        counts[label] = int(result.scalar_one())
    return counts


@router.delete("/{user_id}", status_code=204)
async def delete_account(
    user_id: uuid.UUID,
    purge: bool = False,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete an account.

    ``works.user_id``, ``series.user_id``, and ``conversations.user_id`` are all
    declared ``ondelete="CASCADE"``, so this destroys everything the account
    owns wherever foreign keys are enforced, which is always on Postgres. An
    account holding content is therefore refused unless ``purge=true`` is passed,
    and the refusal says what would have been destroyed. Deactivate instead to
    revoke access while keeping the manuscripts.
    """
    user = await _load(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="Cannot delete your own account")
    if user.is_admin and await _count_other_active_admins(db, user.id) == 0:
        raise HTTPException(
            status_code=409, detail="Cannot remove the last active administrator"
        )

    counts = await _owned_content_counts(db, user.id)
    total = sum(counts.values())
    if total and not purge:
        summary = ", ".join(f"{n} {label}" for label, n in counts.items() if n)
        logger.warning(
            "Refused delete of %s: would cascade-delete %s", user.email, summary
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"{user.email} owns {summary}, which deleting would destroy. "
                "Deactivate the account instead, or pass purge=true to confirm."
            ),
        )

    await db.delete(user)
    await db.commit()
    if total:
        logger.warning(
            "%s purged account %s and its content (%s)",
            admin.email, user.email, counts,
        )
    else:
        logger.warning("%s deleted empty account %s", admin.email, user.email)
