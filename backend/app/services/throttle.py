"""Brute-force protection for password checks.

Failures are counted in a sliding window under three keys, and a request is
refused before the password is checked once any key is over its limit:

* the account from this client: a guessing attack on one account from one place
* the account from anywhere: the same attack spread across many addresses
* the client across accounts: one address trying many accounts

The client address comes from the proxy headers uvicorn is told to trust, and a
client talking to the container directly can forge those. The per-account limit
does not depend on the address, so it holds regardless.

Refusing before verification also spares the PBKDF2 work, so a flood of guesses
cannot tie up the server. A successful sign-in clears that account's failures.

State is in memory, which matches the deployment: one replica at most, and a
restart that forgets recent failures costs an attacker nothing they could not
get by waiting out the window.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 15 * 60


@dataclass(frozen=True)
class Limits:
    per_account_and_client: int = 5
    per_account: int = 20
    per_client: int = 30


class ThrottledError(Exception):
    """Too many recent failures. ``retry_after`` is in whole seconds."""

    def __init__(self, retry_after: int):
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


class FailureThrottle:
    # Enough for any real install; past it the oldest keys are dropped, so a
    # flood of invented account names cannot grow memory without bound.
    MAX_KEYS = 10_000

    def __init__(self, limits: Limits | None = None, clock: Callable[[], float] = time.monotonic):
        self.limits = limits or Limits()
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _keys(self, account: str, client: str) -> list[tuple[str, int]]:
        account = account.strip().lower()
        return [
            (f"pair:{account}|{client}", self.limits.per_account_and_client),
            (f"account:{account}", self.limits.per_account),
            (f"client:{client}", self.limits.per_client),
        ]

    def _recent(self, key: str, now: float) -> deque[float]:
        times = self._failures.get(key)
        if times is None:
            return deque()
        while times and now - times[0] >= WINDOW_SECONDS:
            times.popleft()
        if not times:
            del self._failures[key]
        return times

    def check(self, account: str, client: str) -> None:
        """Raise ThrottledError if this attempt must not even be checked."""
        now = self._clock()
        waits = []
        for key, limit in self._keys(account, client):
            times = self._recent(key, now)
            if len(times) >= limit:
                # Allowed again once enough of the oldest failures age out.
                waits.append(times[len(times) - limit] + WINDOW_SECONDS - now)
        if waits:
            retry_after = max(1, math.ceil(max(waits)))
            logger.warning(
                "Refusing password check for %s from %s: throttled for %ds",
                account, client, retry_after,
            )
            raise ThrottledError(retry_after)

    def record_failure(self, account: str, client: str) -> None:
        now = self._clock()
        for key, _ in self._keys(account, client):
            self._recent(key, now)
            self._failures.setdefault(key, deque()).append(now)
        while len(self._failures) > self.MAX_KEYS:
            self._failures.pop(next(iter(self._failures)))
        logger.debug("Recorded failed password check for %s from %s", account, client)

    def record_success(self, account: str, client: str) -> None:
        """Clear the account's failures. The client's count is left alone, so a
        guesser cannot reset their address limit by signing in to their own account."""
        for key, _ in self._keys(account, client)[:2]:
            self._failures.pop(key, None)
        logger.debug("Cleared failed password checks for %s", account)

    def reset(self) -> None:
        self._failures.clear()


# One per process: sign-in and the current-password check on password change.
password_checks = FailureThrottle()


def retry_message(retry_after: int) -> str:
    minutes = math.ceil(retry_after / 60)
    when = "a minute" if minutes <= 1 else f"{minutes} minutes"
    return f"Too many failed sign-in attempts. Try again in {when}."
