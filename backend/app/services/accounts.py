"""Which way an account signs in, and the rules that keep it to one.

Every account has exactly one sign-in method (``users.auth_provider``):

* ``password``: email and password. The only method with a usable password.
* ``microsoft`` / ``google``: Typecast's own OpenID Connect sign-in.
* ``external``: an authenticating proxy (TYPECAST_AUTH_MODE=proxy).
* ``None``: created by an administrator for single sign-on, not signed in to
  yet. Its first sign-in with a provider decides which.

The rules:

1. An identity already bound to an account signs in to it.
2. Otherwise a provider sign-in whose email the provider vouches for finds the
   account with that email. A password account converts to the provider (its
   password stops working); an unclaimed account is claimed; an account bound
   to anything else is refused, naming the method it uses.
3. Otherwise, the first sign-in to an empty install becomes its administrator,
   and with open registration anyone may create an account. Everyone else is
   told to ask an administrator.

Password sign-in to an account that uses a provider is refused with the name of
the provider, not "Invalid credentials": being told to use Google is the point.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

PASSWORD = "password"
MICROSOFT = "microsoft"
GOOGLE = "google"
EXTERNAL = "external"

PROVIDERS = (MICROSOFT, GOOGLE)
METHODS = (PASSWORD, MICROSOFT, GOOGLE, EXTERNAL)

LABELS = {
    PASSWORD: "a password",
    MICROSOFT: "Microsoft",
    GOOGLE: "Google",
    EXTERNAL: "single sign-on",
}


class AccountError(Exception):
    """A sign-in that cannot be tied to an account. ``status`` is the HTTP code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Identity:
    """Who a provider says signed in.

    ``email_trusted`` is whether the provider vouches for ``email``: only then
    may it be used to find an existing account. An email the provider merely
    passes along is what an attacker could set on an account they control.
    """

    provider: str
    subject: str
    email: str
    name: str
    email_trusted: bool


def unusable_password() -> str:
    """A hash nobody knows the password to, for accounts with no password."""
    from app.services.auth import hash_password

    return hash_password(secrets.token_urlsafe(32))


def uses(user: User, method: str) -> bool:
    return (user.auth_provider or None) == method


def password_refusal(user: User) -> str | None:
    """Why this account cannot sign in with a password, or None if it can."""
    method = user.auth_provider
    if method == PASSWORD:
        return None
    if method is None:
        return (
            "This account is set up for single sign-on. Sign in with Microsoft or Google."
        )
    return f"This account signs in with {LABELS.get(method, method)}. Use that button instead."


def method_refusal(user: User, method: str) -> str:
    want = LABELS.get(user.auth_provider or "", "another method")
    return f"This account signs in with {want}, not {LABELS.get(method, method)}."


async def _count_users(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(User))).scalar_one())


def _username_base(identity: Identity) -> str:
    base = identity.email.split("@")[0] if identity.email else identity.provider
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._-") or "user"
    return cleaned[:80]


async def _free_username(db: AsyncSession, base: str) -> str:
    candidate, n = base, 1
    while (await db.execute(select(User.id).where(User.username == candidate))).first():
        n += 1
        candidate = f"{base}{n}"
    return candidate


async def account_for(
    db: AsyncSession, identity: Identity, *, open_registration: bool = False
) -> User:
    """The account a provider sign-in belongs to, binding or creating it as the rules allow."""
    if identity.provider not in METHODS or identity.provider == PASSWORD:
        raise ValueError(f"not a provider: {identity.provider}")

    # 1. Already bound.
    user = (
        await db.execute(select(User).where(User.external_id == identity.subject))
    ).scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise AccountError(403, "This account has been disabled")
        if uses(user, identity.provider):
            return user
        if user.auth_provider == EXTERNAL and identity.provider == MICROSOFT:
            # Linked through Easy Auth before sign-in moved into the app. Entra's
            # object ID is the same either way, so this is the same person.
            user.auth_provider = MICROSOFT
            await db.commit()
            logger.warning("Moved %s from proxy sign-in to Microsoft", user.email)
            return user
        raise AccountError(403, method_refusal(user, identity.provider))

    # 2. Found by an email the provider vouches for.
    if identity.email:
        candidate = (
            await db.execute(
                select(User).where(func.lower(User.email) == identity.email.lower())
            )
        ).scalar_one_or_none()
        if candidate is not None:
            if not identity.email_trusted:
                logger.warning(
                    "Refused %s sign-in for %s: the provider does not vouch for the email",
                    identity.provider, identity.email,
                )
                raise AccountError(
                    403,
                    f"{LABELS[identity.provider]} could not confirm that "
                    f"{identity.email} is yours, so it cannot be used to sign in to "
                    "the account with that email.",
                )
            if not candidate.is_active:
                raise AccountError(403, "This account has been disabled")
            if candidate.external_id:
                # Bound to a different identity at the same or another provider.
                raise AccountError(403, method_refusal(candidate, identity.provider))
            if candidate.auth_provider not in (None, PASSWORD, identity.provider):
                raise AccountError(403, method_refusal(candidate, identity.provider))
            previous = candidate.auth_provider
            candidate.auth_provider = identity.provider
            candidate.external_id = identity.subject
            # The password stops working: one way in per account.
            candidate.hashed_password = unusable_password()
            await db.commit()
            logger.warning(
                "Account %s now signs in with %s (was %s)",
                candidate.email, identity.provider, previous or "unclaimed",
            )
            return candidate

    # 3. A new account.
    empty = await _count_users(db) == 0
    if not (empty or open_registration):
        logger.info(
            "%s sign-in with no account: %s (%s)",
            identity.provider, identity.email, identity.subject,
        )
        who = identity.email or "your sign-in"
        raise AccountError(
            403, f"There is no Typecast account for {who}. Ask an administrator to add you."
        )
    user = User(
        email=identity.email or f"{identity.subject}@{identity.provider}.invalid",
        username=await _free_username(db, _username_base(identity)),
        display_name=identity.name or identity.email or "New author",
        hashed_password=unusable_password(),
        is_admin=empty,
        auth_provider=identity.provider,
        external_id=identity.subject,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent sign-in created it first; look again.
        await db.rollback()
        return await account_for(db, identity, open_registration=open_registration)
    await db.refresh(user)
    logger.warning(
        "%s sign-in created %s%s",
        identity.provider, user.email, " as the first administrator" if empty else "",
    )
    return user
