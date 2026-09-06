"""Tests for the outbound request guard."""

from __future__ import annotations

import pytest

from app.core.security.ssrf import SsrfBlockedError, SsrfGuard

ALLOWED = frozenset({"generativelanguage.googleapis.com"})


async def test_the_configured_destination_is_permitted():
    """The one address we actually need is allowed through."""
    await SsrfGuard(ALLOWED).check("https://generativelanguage.googleapis.com/v1beta/models")


async def test_an_unlisted_host_is_refused():
    """An allowlist refuses anything it does not recognise."""
    with pytest.raises(SsrfBlockedError, match="not on the outbound allowlist"):
        await SsrfGuard(ALLOWED).check("https://evil.example.com/collect")


async def test_plain_http_is_refused():
    """Unencrypted requests would expose prompt content on the network path."""
    with pytest.raises(SsrfBlockedError, match="scheme is not permitted"):
        await SsrfGuard(ALLOWED).check("http://generativelanguage.googleapis.com/v1beta")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",       # loopback — services bound to localhost
        "10.0.0.5",        # private network
        "192.168.1.1",     # home network
        "172.16.0.1",      # private network
        "169.254.169.254", # the cloud metadata address that hands out credentials
        "::1",             # IPv6 loopback
        "fd00::1",         # IPv6 private
    ],
)
def test_internal_addresses_are_recognised_as_unsafe(address):
    """Every address range an SSRF attack aims for is classified as private.

    169.254.169.254 is the one that matters most: on most cloud platforms it is
    the metadata service, and fetching from it returns credentials.
    """
    assert SsrfGuard._is_public(address) is False  # noqa: SLF001 - testing internals deliberately


@pytest.mark.parametrize("address", ["8.8.8.8", "142.250.187.206", "2001:4860:4860::8888"])
def test_public_addresses_are_recognised_as_safe(address):
    """Genuine internet addresses are not blocked."""
    assert SsrfGuard._is_public(address) is True  # noqa: SLF001


def test_an_unparseable_address_is_treated_as_unsafe():
    """When the guard cannot understand something, the answer is no."""
    assert SsrfGuard._is_public("not-an-address") is False  # noqa: SLF001


async def test_a_url_with_no_hostname_is_refused():
    """Malformed URLs are refused rather than guessed at."""
    with pytest.raises(SsrfBlockedError):
        await SsrfGuard(ALLOWED).check("https:///no-host")
