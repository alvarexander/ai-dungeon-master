"""Application configuration, read from environment variables and validated.

WHY CONFIGURATION LIVES HERE AND NOT IN THE CODE
An "environment variable" is a setting handed to a program by whatever starts
it, rather than written inside the program. Two things force that separation:

1. Secrets. The Gemini API key must not appear in any file that gets committed
   to version control, because version control history is forever and is often
   made public later.
2. Portability. The web address of the frontend differs between your laptop
   and the real server. If it were written into the code, deploying would mean
   editing code, and editing code to deploy is how mistakes happen.

There are deliberately NO localhost defaults anywhere in this file. If a value
is missing the application refuses to start and says which one. A default that
silently works on a laptop is a default that silently breaks in production.

THE FAIL-CLOSED RULE
`Settings.validate_production_safety` runs at import time. When APP_ENV is
"production" it refuses to start the application if any development shortcut is
still switched on. Crashing on startup is loud and fixable; running in
production with a development encryption key is neither.
"""

from __future__ import annotations

import base64
import functools
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]
EncryptionProvider = Literal["local", "aws_kms"]
RepositoryBackend = Literal["memory", "mysql"]


class RateLimitRule:
    """One rate limit, parsed from a string like ``5/900``.

    A rate limit answers "how many times may this be done, in how long?".
    ``5/900`` means five requests per nine hundred seconds (fifteen minutes).

    Attributes:
        limit: How many requests are permitted inside the window.
        window_seconds: The length of the window, in seconds.
    """

    __slots__ = ("limit", "window_seconds")

    def __init__(self, limit: int, window_seconds: int) -> None:
        """Store a parsed limit.

        Args:
            limit: Maximum requests allowed in the window.
            window_seconds: Window length in seconds.
        """
        self.limit = limit
        self.window_seconds = window_seconds

    @classmethod
    def parse(cls, raw: str) -> RateLimitRule:
        """Turn a ``"requests/seconds"`` string into a rule object.

        Args:
            raw: A string such as ``"20/60"``.

        Returns:
            The parsed rule.

        Raises:
            ValueError: If the string is not two positive integers separated
                by a forward slash. Failing here means a typo in configuration
                stops the application at startup rather than silently
                disabling a rate limit, which would be a security hole.
        """
        try:
            limit_text, window_text = raw.split("/", 1)
            limit, window = int(limit_text), int(window_text)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"Rate limit {raw!r} is malformed. Expected '<requests>/<seconds>', e.g. '5/900'."
            ) from exc
        if limit <= 0 or window <= 0:
            raise ValueError(f"Rate limit {raw!r} must use positive numbers on both sides.")
        return cls(limit=limit, window_seconds=window)

    def __repr__(self) -> str:
        """Return a readable representation for logs and error messages."""
        return f"RateLimitRule({self.limit}/{self.window_seconds}s)"


class Settings(BaseSettings):
    """Every setting the backend needs, validated on startup.

    Each field maps to one environment variable of the same name in upper
    case. `.env.example` documents all of them in plain language; this class
    is the machine-readable half of the same contract.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment -------------------------------------------------
    app_env: Environment = "local"
    app_name: str = "AI Dungeon Master API"

    # --- Network -----------------------------------------------------
    # No default. A missing value must stop startup, not quietly become
    # localhost and then fail confusingly after deployment.
    cors_allowed_origins: str
    host: str = "127.0.0.1"
    port: int = 8000

    # --- Gemini ------------------------------------------------------
    gemini_api_key: SecretStr
    gemini_model_id: str = "gemini-3.5-flash"
    gemini_base_url: str
    gemini_timeout_seconds: float = 30.0
    gemini_max_retries: int = 2
    scrub_outbound_prompts: bool = True

    # --- Encryption --------------------------------------------------
    encryption_provider: EncryptionProvider = "local"
    local_dev_master_key: SecretStr
    kms_key_arn: str = ""
    kms_audit_key_arn: str = ""
    aws_region: str = "eu-west-2"
    blind_index_key: SecretStr
    ip_hash_secret: SecretStr

    # --- Authentication ----------------------------------------------
    # "stub"  — Phase 1. Registration and password checking are real, but
    #           sessions are placeholder tokens that grant access to whoever
    #           presents them. Fine locally; catastrophic in production.
    # "real"  — Phase 2. Signed, expiring tokens backed by the sessions table.
    auth_mode: Literal["stub", "real"] = "stub"

    # --- Storage -----------------------------------------------------
    repository_backend: RepositoryBackend = "memory"
    database_url: SecretStr = SecretStr("")
    database_ssl_ca_path: str = ""

    # --- XSRF --------------------------------------------------------
    xsrf_cookie_name: str = "XSRF-TOKEN"
    xsrf_header_name: str = "X-XSRF-TOKEN"
    cookie_secure: bool = False
    # Which domain the XSRF cookie is scoped to. Empty means "this host only",
    # which is correct locally. In production this must be the shared parent
    # domain (e.g. ".example.com") so that the Angular app on app.example.com
    # can read a cookie set by the API on api.example.com — see the note in
    # app/middleware/xsrf.py, which explains why this is not optional.
    cookie_domain: str = ""

    # --- Rate limits (raw strings; parsed below) ---------------------
    rate_limit_ip_global: str = "300/60"
    rate_limit_login: str = "5/900"
    rate_limit_register: str = "3/3600"
    rate_limit_chat: str = "20/60"
    rate_limit_stt: str = "10/60"
    rate_limit_password_reset: str = "3/3600"

    # --- Speech to text ----------------------------------------------
    stt_enabled: bool = True
    stt_model_size: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_max_seconds: int = 120
    stt_max_upload_bytes: int = 10 * 1024 * 1024

    # --- Logging and telemetry ---------------------------------------
    log_format: Literal["json", "console"] = "console"
    log_level: str = "INFO"
    log_redaction_enabled: bool = True
    sentry_dsn: str = ""
    debug_capture_ttl_hours: int = Field(default=48, le=48)
    support_grant_ttl_seconds: int = Field(default=3600, le=86400)

    # -----------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------

    @field_validator("cors_allowed_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: str) -> str:
        """Refuse a wildcard CORS origin.

        ``*`` tells the browser that any website may read this API's replies.
        Combined with cookie-based sessions that is a serious hole, and
        browsers refuse the combination anyway — so a wildcard here would
        produce a confusing runtime failure instead of a clear startup one.

        Args:
            value: The comma-separated origins from configuration.

        Returns:
            The value unchanged, if acceptable.

        Raises:
            ValueError: If a wildcard is present or the list is empty.
        """
        if not value.strip():
            raise ValueError(
                "CORS_ALLOWED_ORIGINS is empty. Set it to the frontend's address, "
                "for example http://localhost:4200 during local development."
            )
        if "*" in value:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*'. List each exact origin, "
                "for example: https://app.example.com,https://www.example.com"
            )
        return value

    @field_validator("local_dev_master_key", "blind_index_key", "ip_hash_secret")
    @classmethod
    def _must_be_base64(cls, value: SecretStr) -> SecretStr:
        """Confirm a secret is valid base64 and long enough to be a real key.

        Base64 is a way of writing raw bytes using ordinary letters and digits
        so they survive being pasted into a text file. A key that fails to
        decode would otherwise cause a confusing error deep inside the
        encryption code, long after startup.

        Args:
            value: The secret as read from the environment.

        Returns:
            The value unchanged, if acceptable.

        Raises:
            ValueError: If the value is not base64, or decodes to fewer than
                16 bytes, which is too short to be a serious key.
        """
        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except Exception as exc:  # noqa: BLE001 - any decode failure is fatal
            raise ValueError(
                "Secret is not valid base64. Generate one with: "
                'python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
            ) from exc
        if len(decoded) < 16:
            raise ValueError(
                f"Secret decodes to only {len(decoded)} bytes; at least 16 are required. "
                "Generate a 32-byte key instead."
            )
        return value

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        """Refuse to start in production with any development shortcut enabled.

        This is the fail-closed rule. Each check below corresponds to a
        setting that is perfectly reasonable on a laptop and unacceptable on a
        real server. Rather than trusting whoever deploys to remember, the
        application simply will not start.

        Returns:
            The validated settings object.

        Raises:
            ValueError: Listing every unsafe setting found, so they can all be
                fixed in one pass rather than one restart at a time.
        """
        if self.app_env != "production":
            return self

        problems: list[str] = []

        if self.encryption_provider != "aws_kms":
            problems.append(
                "ENCRYPTION_PROVIDER is 'local', which uses a key written down in a file. "
                "Production must use 'aws_kms'."
            )
        if not self.kms_key_arn:
            problems.append("KMS_KEY_ARN is empty but is required when using AWS KMS.")
        if self.auth_mode != "real":
            problems.append(
                "AUTH_MODE is 'stub', which accepts any placeholder token as proof of "
                "identity. Production must use 'real'."
            )
        if not self.log_redaction_enabled:
            problems.append(
                "LOG_REDACTION_ENABLED is false, which would allow personal data into logs."
            )
        if not self.cookie_secure:
            problems.append(
                "COOKIE_SECURE is false, which would let session cookies travel unencrypted."
            )
        if any(origin.startswith("http://") for origin in self.cors_origin_list):
            problems.append(
                "CORS_ALLOWED_ORIGINS contains a plain http:// address. Production must be https://."
            )
        if self.repository_backend == "mysql" and not self.database_ssl_ca_path:
            problems.append(
                "DATABASE_SSL_CA_PATH is empty. The database connection must use TLS."
            )
        if self.log_format != "json":
            problems.append("LOG_FORMAT should be 'json' in production so logs can be searched.")

        if problems:
            bullets = "\n  - ".join(problems)
            raise ValueError(
                "Refusing to start: APP_ENV is 'production' but unsafe settings remain:\n  - "
                f"{bullets}\n"
                "Each of these is safe locally and unacceptable in production. "
                "See docs/SECURITY.md."
            )
        return self

    # -----------------------------------------------------------------
    # Derived values
    # -----------------------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        """Split the configured origins into a clean list.

        Returns:
            Each allowed origin, trimmed, with empty entries and trailing
            slashes removed. A trailing slash is the single most common cause
            of a CORS origin failing to match, so it is stripped here rather
            than left to cause a mysterious browser error.
        """
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_local(self) -> bool:
        """Return True when running on a developer's machine."""
        return self.app_env == "local"

    @property
    def uses_insecure_dev_encryption(self) -> bool:
        """Return True when encryption uses the written-down development key.

        Used to emit a loud startup warning. Data really is encrypted in this
        mode, but with a key anyone can read, so it protects nothing.
        """
        return self.encryption_provider == "local"

    @functools.cached_property
    def rate_limits(self) -> dict[str, RateLimitRule]:
        """Parse every rate limit string into a usable rule.

        Returns:
            A mapping of scope name to rule. Scope names match the ``scope``
            enum in the database schema so that the in-memory Phase 1 limiter
            and the Phase 2 SQL limiter agree on vocabulary.

        Raises:
            ValueError: If any limit string is malformed.
        """
        return {
            "ip_global": RateLimitRule.parse(self.rate_limit_ip_global),
            "login": RateLimitRule.parse(self.rate_limit_login),
            "register": RateLimitRule.parse(self.rate_limit_register),
            "chat": RateLimitRule.parse(self.rate_limit_chat),
            "stt": RateLimitRule.parse(self.rate_limit_stt),
            "password_reset": RateLimitRule.parse(self.rate_limit_password_reset),
        }

    @functools.cached_property
    def outbound_allowed_hosts(self) -> frozenset[str]:
        """Return the only hostnames this server may make requests to.

        This is the allowlist used by the SSRF guard. SSRF (Server-Side
        Request Forgery) is an attack where a user tricks your server into
        making a request on their behalf — often to an address only your
        server can reach, such as a cloud provider's internal credential
        service. The defence is to decide in advance where the server is
        permitted to connect, and refuse everything else.

        The list is derived from configuration rather than written into the
        code, so changing the Gemini address in one place updates both the
        client and its guard, and they cannot disagree.

        Returns:
            The set of permitted hostnames.
        """
        from urllib.parse import urlparse

        hosts = {urlparse(self.gemini_base_url).hostname or ""}
        return frozenset(host for host in hosts if host)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load the settings once and reuse them for the lifetime of the process.

    Reading and validating environment variables on every request would be
    wasteful, so the result is cached. FastAPI's dependency injection calls
    this function, which makes the settings easy to replace in tests: a test
    clears the cache and sets different environment variables.

    Returns:
        The validated application settings.
    """
    return Settings()  # type: ignore[call-arg]  # values come from the environment
