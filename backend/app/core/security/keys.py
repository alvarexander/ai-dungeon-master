"""Key providers: where Data Encryption Keys come from and how they are wrapped.

THE IDEA IN ONE PARAGRAPH
Every user's personal data is locked with a key belonging to that user alone —
their Data Encryption Key, or DEK. We cannot store that key next to the data,
because an attacker who steals the data would steal the key with it. So we lock
the key itself inside a second lock that only a key-management service can
open, and store the locked-up key beside the data. The locked-up form is called
a "wrapped" key, and the whole arrangement is "envelope encryption": a key in
an envelope, sitting next to what it opens.

WHY THERE ARE TWO PROVIDERS
`AwsKmsKeyProvider` is the real one. AWS Key Management Service holds the
master key inside hardware that never reveals it; we send it a wrapped key and
it sends back the unwrapped one, having checked that we are allowed to ask.

`LocalDevKeyProvider` does the same operations using a master key written down
in the `.env` file. Data is genuinely encrypted, so the code path is exercised
exactly as it will be in production — but the key is readable by anyone with
the file, so it protects nothing. That is intentional: locally you want to be
able to inspect everything. The application logs a loud warning when this
provider is active and refuses to start with it when APP_ENV is production.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings

# The size of a Data Encryption Key, in bytes. 32 bytes is 256 bits, which is
# what AES-256 requires.
DEK_LENGTH_BYTES = 32

# AES-GCM uses a "nonce": a number used once. It does not need to be secret,
# but reusing one with the same key destroys the encryption's guarantees
# entirely, so it is always randomly generated and never reused.
NONCE_LENGTH_BYTES = 12


class KeyProviderError(RuntimeError):
    """Raised when a key cannot be created or unwrapped.

    This is deliberately a hard failure rather than something the caller can
    shrug off. If a key cannot be unwrapped, the correct behaviour is to fail
    the request — never to fall back to storing something in plaintext.
    """


class KeyProvider(Protocol):
    """The contract every key provider satisfies.

    A Protocol in Python describes a shape rather than a base class: any object
    with these two methods can be used as a key provider. This is what lets the
    development and AWS implementations be swapped by changing one environment
    variable, with no other code aware of the difference.
    """

    def generate_data_key(self) -> tuple[bytes, bytes]:
        """Create a brand new Data Encryption Key for one user.

        Returns:
            A pair of ``(plaintext_key, wrapped_key)``. The plaintext key is
            used immediately and then discarded from memory; only the wrapped
            form is ever written to the database.
        """
        ...

    def unwrap_data_key(self, wrapped: bytes) -> bytes:
        """Recover a usable key from its wrapped form.

        Args:
            wrapped: The bytes stored in the database.

        Returns:
            The plaintext Data Encryption Key.

        Raises:
            KeyProviderError: If the key cannot be unwrapped.
        """
        ...


class LocalDevKeyProvider:
    """Development-only provider using a fixed master key from configuration.

    INSECURE BY DESIGN. The master key is in the `.env` file, so anyone who can
    read that file can decrypt everything. Its purpose is to let you inspect
    data freely while building, while still running the identical code path
    that production will run.
    """

    def __init__(self, master_key_b64: str) -> None:
        """Set up the provider from a base64-encoded master key.

        Args:
            master_key_b64: The development master key, base64 encoded. Padded
                or truncated to exactly 32 bytes so that a short value in a
                `.env` file produces a working development environment rather
                than a confusing crash.
        """
        raw = base64.b64decode(master_key_b64)
        self._master_key = raw[:32].ljust(32, b"\0")
        self._aead = AESGCM(self._master_key)

    def generate_data_key(self) -> tuple[bytes, bytes]:
        """Create a random key and wrap it under the development master key.

        Returns:
            The plaintext key and its wrapped form.
        """
        plaintext = os.urandom(DEK_LENGTH_BYTES)
        nonce = os.urandom(NONCE_LENGTH_BYTES)
        # The associated data ties this wrapped key to its purpose, so a
        # wrapped key cannot be reused somewhere it was not meant to go.
        wrapped = nonce + self._aead.encrypt(nonce, plaintext, b"dek-wrap-v1")
        return plaintext, wrapped

    def unwrap_data_key(self, wrapped: bytes) -> bytes:
        """Unwrap a key that was wrapped by this provider.

        Args:
            wrapped: The stored wrapped key.

        Returns:
            The plaintext Data Encryption Key.

        Raises:
            KeyProviderError: If the bytes are truncated or have been tampered
                with. Note that this also happens, correctly, when a key was
                wrapped under a different master key — for example after
                changing LOCAL_DEV_MASTER_KEY, which invalidates all existing
                local data.
        """
        if len(wrapped) <= NONCE_LENGTH_BYTES:
            raise KeyProviderError("Wrapped key is too short to be valid.")
        nonce, body = wrapped[:NONCE_LENGTH_BYTES], wrapped[NONCE_LENGTH_BYTES:]
        try:
            return self._aead.decrypt(nonce, body, b"dek-wrap-v1")
        except Exception as exc:  # noqa: BLE001 - all failures are equally fatal
            raise KeyProviderError(
                "Could not unwrap the data key with the local development master key. "
                "If you changed LOCAL_DEV_MASTER_KEY, existing local data is now "
                "unreadable — which is exactly what crypto-shredding does in production."
            ) from exc


class AwsKmsKeyProvider:
    """Production provider backed by AWS Key Management Service.

    KMS is a service that holds master keys inside tamper-resistant hardware.
    The key never leaves that hardware. We ask KMS to "generate a data key",
    and it returns a new random key twice: once in the clear for immediate use,
    and once encrypted under the master key for storage. Later we hand back the
    encrypted copy and KMS returns the clear one — but only if the identity
    making the request is permitted to ask.

    That last clause is what makes the key custody requirement enforceable: the
    KMS policy grants Decrypt to the application's role and denies it to the
    everyday administrator role, so an administrator with full database access
    still cannot read user data.
    """

    def __init__(self, key_arn: str, region: str) -> None:
        """Prepare a KMS-backed provider.

        Args:
            key_arn: Which master key to use. An ARN (Amazon Resource Name) is
                AWS's way of naming a thing. It names the key; it is not the
                key, and is not a secret.
            region: The AWS region the key lives in.

        Raises:
            KeyProviderError: If the optional AWS libraries are not installed.
        """
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise KeyProviderError(
                "ENCRYPTION_PROVIDER is 'aws_kms' but the AWS libraries are not "
                "installed. Install them with: uv sync --extra aws"
            ) from exc

        self._key_arn = key_arn
        # No credentials are passed here on purpose. On Fly.io the AWS SDK
        # picks up short-lived credentials obtained through OIDC federation
        # (see ADR-012), so there is no long-lived access key anywhere.
        self._client = boto3.client("kms", region_name=region)

    def generate_data_key(self) -> tuple[bytes, bytes]:
        """Ask KMS for a new data key.

        Returns:
            The plaintext key and its KMS-wrapped form.

        Raises:
            KeyProviderError: If KMS refuses or is unreachable.
        """
        try:
            response = self._client.generate_data_key(KeyId=self._key_arn, KeySpec="AES_256")
        except Exception as exc:  # noqa: BLE001 - surfaced as a single failure mode
            raise KeyProviderError(f"AWS KMS refused to generate a data key: {exc}") from exc
        return response["Plaintext"], response["CiphertextBlob"]

    def unwrap_data_key(self, wrapped: bytes) -> bytes:
        """Ask KMS to unwrap a stored key.

        Args:
            wrapped: The ``CiphertextBlob`` previously stored in the database.

        Returns:
            The plaintext Data Encryption Key.

        Raises:
            KeyProviderError: If KMS refuses. In production this call is
                monitored: every Decrypt is recorded in CloudTrail, and an
                alert fires on any call made by the break-glass role.
        """
        try:
            response = self._client.decrypt(CiphertextBlob=wrapped, KeyId=self._key_arn)
        except Exception as exc:  # noqa: BLE001
            raise KeyProviderError(f"AWS KMS refused to unwrap the data key: {exc}") from exc
        return response["Plaintext"]


def build_key_provider(settings: Settings) -> KeyProvider:
    """Choose the key provider named by configuration.

    Args:
        settings: The validated application settings.

    Returns:
        A ready-to-use key provider.

    Raises:
        KeyProviderError: If AWS KMS is selected without a key being named.
            Failing here rather than at first use means the problem appears at
            startup, not at three in the morning on the first registration.
    """
    if settings.encryption_provider == "aws_kms":
        if not settings.kms_key_arn:
            raise KeyProviderError("ENCRYPTION_PROVIDER is 'aws_kms' but KMS_KEY_ARN is empty.")
        return AwsKmsKeyProvider(settings.kms_key_arn, settings.aws_region)
    return LocalDevKeyProvider(settings.local_dev_master_key.get_secret_value())
