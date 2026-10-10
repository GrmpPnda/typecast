"""Sign-in with Microsoft or Google: start, callback, and code exchange.

Public by necessity, since they are how someone with no session gets one. The
protections are in app/services/oidc.py: state bound to the browser's cookie and
usable once, PKCE, nonce, a fully verified ID token, and a single-use code in
place of a token in any URL.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.user import User
from app.services import accounts, oidc
from app.services import auth as auth_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ExchangeRequest(BaseModel):
    code: str


def _require_multi_mode() -> None:
    if auth_service.AUTH_MODE != "multi":
        raise oidc.OIDCError(400, "Sign-in with a provider needs multi-user mode.")


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _back_to_login(**params: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?{urlencode(params)}", status_code=302)
    response.delete_cookie(oidc.STATE_COOKIE, path=oidc.COOKIE_PATH)
    return response


@router.get("/{provider_id}/start")
async def start(provider_id: str, request: Request):
    try:
        _require_multi_mode()
        state, url = await oidc.begin(provider_id, _base_url(request))
    except oidc.OIDCError as exc:
        return _back_to_login(sso_error=str(exc))
    response = RedirectResponse(url, status_code=302)
    # Lax, not Strict: the provider's redirect back is a cross-site navigation,
    # and a Strict cookie would not come with it.
    response.set_cookie(
        oidc.STATE_COOKIE, state, max_age=oidc.PENDING_TTL, path=oidc.COOKIE_PATH,
        httponly=True, secure=request.url.scheme == "https", samesite="lax",
    )
    return response


@router.get("/{provider_id}/callback")
async def callback(
    provider_id: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_multi_mode()
        if error:
            # The person cancelled, or the provider refused (for example, a user
            # not assigned to the app in Entra ID).
            logger.info("%s sign-in ended with %s: %s", provider_id, error, error_description)
            raise oidc.OIDCError(400, _provider_error(provider_id, error, error_description))
        pending = oidc.take_pending(provider_id, state, request.cookies.get(oidc.STATE_COOKIE))
        identity = await oidc.identity_from_code(provider_id, code, pending)
        user = await accounts.account_for(
            db, identity, open_registration=auth_service.OPEN_REGISTRATION
        )
    except (oidc.OIDCError, accounts.AccountError) as exc:
        return _back_to_login(sso_error=str(exc))
    logger.info("%s sign-in for %s", provider_id, user.email)
    return _back_to_login(sso_code=oidc.issue_code(user.id))


def _provider_error(provider_id: str, error: str, description: str) -> str:
    name = oidc.PROVIDERS[provider_id].name if provider_id in oidc.PROVIDERS else "The provider"
    if error == "access_denied":
        return f"{name} sign-in was cancelled or not allowed for your account."
    # Entra's codes ride in the description, e.g. AADSTS50105 for an unassigned user.
    return f"{name} could not sign you in ({error}). {description.split(chr(10))[0][:200]}".strip()


@router.post("/exchange")
async def exchange(data: ExchangeRequest, db: AsyncSession = Depends(get_db)):
    """Trade the single-use code from the callback for a session."""
    from app.api.auth import _user_response

    try:
        user_id = oidc.redeem_code(data.code)
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return {"token": auth_service.create_access_token(user.id), "user": _user_response(user)}
