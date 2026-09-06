"""Rate limiting, counted against fingerprints rather than identities.

WHAT RATE LIMITING IS
A cap on how often something may be done. "Five login attempts per fifteen
minutes from one address." It is the main defence against three separate
problems: someone guessing passwords, someone probing which email addresses are
registered, and someone burning through the Gemini free tier for fun.

THE PRIVACY PROBLEM, AND WHY IT IS NOT A PROBLEM
Counting per network address normally means storing network addresses, and an
IP address is personal data. That would appear to force a hole in the privacy
design.

It does not. What rate limiting actually needs is a *stable key* — something
that is the same for the same caller and different for a different one. It does
not need the key to be readable. So the key is an HMAC fingerprint of the
address, computed with a salt that rotates daily and is never stored next to
the counters.

The consequence is worth stating plainly: **the entire abuse-prevention path
runs without a single decryption call and without one readable identifier.**
Privacy and security do not trade against each other here — see
:func:`app.core.security.blind_index.BlindIndexService.ip_digest`.

PHASE 1 VERSUS PHASE 2
Phase 1 counts in this server's memory. That is correct for one machine and
wrong for several, because each would keep its own tally. Phase 2 swaps in an
implementation that calls the ``sp_rate_limit_hit`` stored procedure, so all
machines share one counter. Both satisfy the same interface, so nothing else in
the application changes — and both take a digest, never an address.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol

from app.config import RateLimitRule


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The outcome of counting one request against a limit.

    Attributes:
        allowed: Whether the request may proceed.
        hit_count: How many requests have been made in the current window.
        limit: The cap for this scope.
        retry_after_seconds: How long until the window resets. Sent to the
            browser in the ``Retry-After`` header so a well-behaved client
            knows when to try again instead of hammering.
    """

    allowed: bool
    hit_count: int
    limit: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    """The contract shared by the in-memory and database-backed limiters."""

    def hit(self, bucket: bytes, scope: str, rule: RateLimitRule) -> RateLimitResult:
        """Count one request and report whether it is permitted.

        Args:
            bucket: A 32-byte fingerprint of the caller. Never a readable
                address or name.
            scope: Which limit this counts against, e.g. ``"login"``.
            rule: The cap and window for this scope.

        Returns:
            Whether the request is allowed, and when to try again if not.
        """
        ...


class InMemoryRateLimiter:
    """Counts requests in this process's memory. Correct for a single machine.

    Uses a fixed-window counter: time is divided into blocks of
    ``window_seconds``, and each block has its own tally.

    THE KNOWN WEAKNESS OF FIXED WINDOWS
    A caller can make their full allowance at the very end of one window and
    again at the very start of the next, briefly achieving double the intended
    rate. A sliding window avoids this at the cost of storing a timestamp per
    request. For limits whose purpose is to stop automated abuse rather than to
    meter a paid service, the simpler approach is sufficient — an attacker who
    gains ten login attempts in a moment instead of five has gained nothing
    meaningful. The tradeoff is recorded here so it is a decision rather than
    an oversight.
    """

    def __init__(self) -> None:
        """Create an empty limiter."""
        # Maps (bucket, scope, window index) to a count.
        self._counters: dict[tuple[bytes, str, int], int] = {}
        # Requests are handled concurrently, so the counter needs a lock to
        # avoid two of them reading the same value and both writing back one
        # more than it — which would let a caller exceed the limit.
        self._lock = threading.Lock()
        self._last_prune = time.monotonic()

    def hit(self, bucket: bytes, scope: str, rule: RateLimitRule) -> RateLimitResult:
        """Count one request against a limit.

        Args:
            bucket: The caller's 32-byte fingerprint.
            scope: Which limit applies.
            rule: The cap and window.

        Returns:
            The outcome, including how long to wait if the caller is over.
        """
        now = time.time()
        window_index = int(now // rule.window_seconds)
        key = (bucket, scope, window_index)

        with self._lock:
            count = self._counters.get(key, 0) + 1
            self._counters[key] = count
            self._maybe_prune(now, rule.window_seconds)

        window_ends_at = (window_index + 1) * rule.window_seconds
        return RateLimitResult(
            allowed=count <= rule.limit,
            hit_count=count,
            limit=rule.limit,
            retry_after_seconds=max(1, int(window_ends_at - now)),
        )

    def _maybe_prune(self, now: float, window_seconds: int) -> None:
        """Discard counters from windows that have passed.

        Without this the dictionary would grow forever, since every new caller
        and every new window adds an entry that is never removed.

        Args:
            now: The current time.
            window_seconds: The window length, used to decide what is stale.
        """
        if now - self._last_prune < 60:
            return
        self._last_prune = now
        cutoff = int(now // window_seconds) - 1
        stale = [key for key in self._counters if key[2] < cutoff]
        for key in stale:
            self._counters.pop(key, None)

    def reset(self) -> None:
        """Clear every counter. Used by tests, never in normal operation."""
        with self._lock:
            self._counters.clear()
