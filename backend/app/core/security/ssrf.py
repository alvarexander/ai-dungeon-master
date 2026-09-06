"""SSRF protection for every outbound request this server makes.

WHAT SSRF IS
Server-Side Request Forgery is an attack where someone persuades your server to
make a network request on their behalf. The danger is not that your server can
reach the public internet — it is that your server can reach places the
attacker cannot: a cloud provider's internal metadata service that hands out
credentials, a database on a private network, an admin panel bound to localhost.

The classic example: a feature that fetches a user-supplied image URL. The
attacker supplies `http://169.254.169.254/latest/meta-data/iam/security-credentials/`
and your server obediently fetches the cloud credentials and shows them to
them.

THE ANALOGY
Think of your server as a trusted employee inside a building. An attacker
outside cannot walk into the server room, but they can ask the employee to
"just go and read what is written on that door for me". SSRF protection is the
rule that the employee only ever visits addresses on a pre-approved list.

WHY THIS EXISTS EVEN THOUGH GEMINI IS THE ONLY DESTINATION
Today the server only ever calls Google. But defences are built before they are
needed, not after. The first feature that fetches a user-supplied URL — an
avatar image, a campaign import, a webhook — will be written by someone who has
forgotten this conversation. It will use this client because it is the only
HTTP client available, and it will be safe by default.

THE THREE CHECKS
1. **Scheme.** HTTPS only. Plain HTTP would let anyone on the network path read
   the prompts, which contain what players typed.
2. **Hostname allowlist.** The destination must be a host we decided on in
   advance, in configuration. An allowlist, not a blocklist: unknown
   destinations are refused rather than permitted-unless-recognised.
3. **Resolved address.** The hostname is looked up and every address it
   resolves to must be a public one. This catches a hostname on the allowlist
   that has been made to point somewhere internal.

Redirects are refused outright. Following a redirect means visiting an address
that was never checked, which would undo all three checks above.

A NOTE ON THE LIMIT OF CHECK 3
There is a narrow attack called DNS rebinding, where a name resolves to a safe
address when we check it and an unsafe one moments later when we connect.
Closing that gap completely means connecting to a pinned address rather than a
name, which conflicts with certificate validation and connection pooling. Given
that check 2 already restricts destinations to a fixed list of Google
hostnames, the residual risk is very small — but it is real, and it is recorded
here rather than glossed over.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# How long to wait to establish a connection before giving up. A connection
# that has not been accepted in this long is not going to be.
CONNECT_TIMEOUT_SECONDS = 8.0


class SsrfBlockedError(RuntimeError):
    """Raised when an outbound request is refused by the guard.

    Never retried and never downgraded to a warning. A blocked request means
    either a configuration mistake or an attack, and both deserve a failure.
    """


class SsrfGuard:
    """Decides whether this server is permitted to connect to a given URL."""

    def __init__(self, allowed_hosts: frozenset[str], *, require_https: bool = True) -> None:
        """Set up the guard.

        Args:
            allowed_hosts: Exact hostnames the server may contact. Derived from
                configuration, so the client and its guard cannot disagree
                about where Gemini lives.
            require_https: Whether to insist on encrypted connections. Only a
                test would ever set this to False.
        """
        self._allowed_hosts = allowed_hosts
        self._require_https = require_https

    async def check(self, url: str) -> None:
        """Verify a URL is safe to request, or refuse it.

        Args:
            url: The full URL about to be requested.

        Raises:
            SsrfBlockedError: If the URL fails any check. The message names the
                specific reason, because a blocked request during development
                is almost always a missing entry in the allowlist and the
                developer needs to know that immediately.
        """
        parsed = urlparse(url)

        if self._require_https and parsed.scheme != "https":
            raise SsrfBlockedError(
                f"Refused: {parsed.scheme or 'no'} scheme is not permitted. Outbound "
                "requests must use https so that prompt content cannot be read in transit."
            )

        host = parsed.hostname
        if not host:
            raise SsrfBlockedError(f"Refused: {url!r} has no hostname.")

        if host not in self._allowed_hosts:
            allowed = ", ".join(sorted(self._allowed_hosts)) or "(none configured)"
            raise SsrfBlockedError(
                f"Refused: {host!r} is not on the outbound allowlist. Permitted hosts: "
                f"{allowed}. If this is a legitimate new destination, add it to "
                "configuration deliberately — do not widen the allowlist to make an "
                "error go away."
            )

        for address in await self._resolve(host):
            if not self._is_public(address):
                raise SsrfBlockedError(
                    f"Refused: {host!r} resolves to {address}, which is a private, "
                    "loopback, link-local or otherwise internal address. This is the "
                    "signature of an SSRF attempt."
                )

    @staticmethod
    async def _resolve(host: str) -> list[str]:
        """Look up every address a hostname points to.

        Runs the lookup in a worker thread. ``socket.getaddrinfo`` blocks until
        the name server answers, and a blocking call inside asynchronous code
        stops the entire server — every other player's request freezes for as
        long as this one lookup takes. On a healthy network that is a
        millisecond and nobody notices; on a broken one it is fifteen seconds
        of the whole application being unresponsive.

        Args:
            host: The hostname to resolve.

        Returns:
            All resolved addresses, IPv4 and IPv6. Every one is checked,
            because a name that returns one safe and one unsafe address must
            be refused.

        Raises:
            SsrfBlockedError: If the name cannot be resolved at all.
        """
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SsrfBlockedError(
                f"Refused: could not resolve {host!r}. Check your network connection "
                "and that the hostname in configuration is spelled correctly."
            ) from exc
        return [info[4][0] for info in infos]

    @staticmethod
    def _is_public(address: str) -> bool:
        """Report whether an address is on the public internet.

        Args:
            address: An IPv4 or IPv6 address as text.

        Returns:
            True only if the address is globally routable. Private ranges
            (192.168.x.x), loopback (127.0.0.1), link-local (169.254.169.254 —
            the cloud metadata address), multicast and reserved ranges all
            return False. An unparseable address also returns False, because
            the safe answer to "I do not understand this" is "no".
        """
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        return not (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        )


class SafeHttpClient:
    """An HTTP client that checks every request against the SSRF guard.

    This is the only HTTP client the application code should use. It wraps
    httpx and refuses to make a request the guard has not approved.
    """

    def __init__(self, guard: SsrfGuard, *, timeout: float = 30.0) -> None:
        """Create the client.

        Args:
            guard: The guard that approves destinations.
            timeout: How long to wait, in seconds, before giving up. A timeout
                is a security control as well as a reliability one: without it,
                a slow destination can tie up the server indefinitely.
        """
        self._guard = guard
        self._client = httpx.AsyncClient(
            # Two different timeouts, because two different things can go slow
            # and they deserve different patience.
            #
            #   connect — how long to wait to establish a connection at all. A
            #             failure here means the network is down or the host is
            #             unreachable, and waiting longer will not help. Kept
            #             short so an offline machine fails in seconds rather
            #             than leaving the player staring at a spinner.
            #   read    — how long to wait for the model to finish thinking.
            #             This legitimately takes seconds, so it gets the full
            #             configured allowance.
            #
            # Using one timeout for both is the common mistake: either
            # connections hang for the whole read timeout, or slow-but-working
            # generations get cut off.
            timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS),
            # Redirects are not followed. A redirect names a destination that
            # was never checked, which would defeat the guard entirely.
            follow_redirects=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def post_json(
        self, url: str, *, json_body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        """Send a checked JSON POST request.

        Args:
            url: The destination. Checked before any connection is made.
            json_body: The request body, serialised as JSON.
            headers: Extra headers, such as the Gemini API key.

        Returns:
            The raw response, for the caller to interpret.

        Raises:
            SsrfBlockedError: If the guard refuses the destination.
            httpx.HTTPError: On a network failure or timeout.
        """
        await self._guard.check(url)
        return await self._client.post(url, json=json_body, headers=headers or {})

    async def get(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        """Send a checked GET request.

        Args:
            url: The destination. Checked before any connection is made.
            headers: Extra headers.

        Returns:
            The raw response.

        Raises:
            SsrfBlockedError: If the guard refuses the destination.
            httpx.HTTPError: On a network failure or timeout.
        """
        await self._guard.check(url)
        return await self._client.get(url, headers=headers or {})

    async def aclose(self) -> None:
        """Close the underlying connections when the application shuts down."""
        await self._client.aclose()
