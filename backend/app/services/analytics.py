"""The analytics plane: counting activity without recording people.

TWO SEPARATE TELEMETRY SYSTEMS, AND WHY
This application keeps two, with different rules, that never join to each
other:

- **Analytics** (this file). Pseudonymous, aggregated, kept for a long time.
  Answers "how is the product doing?".
- **Debug telemetry** (the logs). Identified by request, kept for 14 days.
  Answers "what happened to this one person just now?".

Keeping them apart is what allows the first to be retained indefinitely without
accumulating a history of anybody.

THE PSEUDONYM
Every user has an ``analytics_id``: a random identifier with no mathematical
relationship to their ``user_id``. The link between the two lives in one
encrypted mapping row. Analytics records reference only the pseudonym.

The payoff appears at deletion. Destroying a user's key and their mapping row
severs the link permanently — but it does *not* delete the events. Their past
activity keeps counting toward the totals as an anonymous contribution that can
never again be traced to anyone. You keep your business metrics; they get real
deletion. Both, not a trade.

THE ALLOWLIST IS A SCHEMA, NOT A CONVENTION
Events accept only declared fields, and every field is an enumerated value, a
boolean, a number, or a timestamp. **There is no free-text field anywhere in
the analytics schema.** That is the mechanism, not a rule someone must
remember: a careless future change cannot smuggle a player's message into
analytics because there is physically nowhere for it to land. Unknown fields
are rejected loudly rather than dropped quietly, so the mistake surfaces during
development instead of silently losing data.

GEOGRAPHY
Country only, and never derived by keeping the address. In production
Cloudflare sits in front of the API and adds a ``CF-IPCountry`` header, so the
country arrives already computed and the address itself is never inspected,
stored, or passed to a lookup service.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.logging import get_logger

_log = get_logger("analytics")

# The complete list of events that may be recorded. Matches the ENUM in
# migrations/0001_initial_schema.sql exactly. Adding an event means changing
# both, in the same commit — which is the moment to ask whether the new event
# reveals anything about a person.
ALLOWED_EVENTS: frozenset[str] = frozenset(
    {
        "session_started",
        "session_ended",
        "turn_taken",
        "voice_input_used",
        "campaign_created",
        "character_created",
        "character_updated",
        "settings_changed",
        "error_occurred",
        "quota_exhausted",
        "signup_completed",
        "login_succeeded",
    }
)

ALLOWED_FEATURES: frozenset[str] = frozenset(
    {"voice_input", "typed_input", "character_sheet", "campaign_list", "dice_roller", "settings"}
)

ALLOWED_ERROR_CATEGORIES: frozenset[str] = frozenset(
    {"validation", "rate_limited", "upstream_ai", "upstream_timeout", "auth", "internal"}
)

# Durations are bucketed rather than exact. An exact session length of
# 1,847 seconds is close to unique and can act as a fingerprint linking records
# together; "30 to 60 minutes" cannot.
DURATION_BUCKETS: list[tuple[float, str]] = [
    (60, "lt_1m"),
    (300, "1_5m"),
    (900, "5_15m"),
    (1800, "15_30m"),
    (3600, "30_60m"),
]


class AnalyticsRejected(ValueError):
    """Raised when an event does not match the allowlist.

    Deliberately an exception rather than a silent drop. A rejected event is a
    programming mistake, and mistakes that fail loudly get fixed while
    mistakes that fail quietly become permanent gaps in the data.
    """


def bucket_duration(seconds: float) -> str:
    """Put a duration into a coarse bucket.

    Args:
        seconds: How long something took.

    Returns:
        A bucket name such as ``"5_15m"``. Coarse on purpose — see the note
        above about exact values acting as fingerprints.
    """
    for threshold, name in DURATION_BUCKETS:
        if seconds < threshold:
            return name
    return "gt_60m"


@dataclass(slots=True)
class AnalyticsEvent:
    """One recorded event. Every field is an enum, a number, or a timestamp.

    Attributes:
        analytics_id: The pseudonym. Never the user's real identifier.
        event_name: One of ``ALLOWED_EVENTS``.
        occurred_at: When it happened, UTC.
        country_code: Two-letter country, or ``None``. Never a city.
        duration_bucket: A coarse duration bucket, or ``None``.
        turn_count: A count, or ``None``.
        feature: One of ``ALLOWED_FEATURES``, or ``None``.
        error_category: One of ``ALLOWED_ERROR_CATEGORIES``, or ``None``.
        success: A boolean, or ``None``.
    """

    analytics_id: UUID
    event_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    country_code: str | None = None
    duration_bucket: str | None = None
    turn_count: int | None = None
    feature: str | None = None
    error_category: str | None = None
    success: bool | None = None


class AnalyticsService:
    """Records events and rolls them into aggregate counters.

    Phase 1 keeps everything in memory. Phase 2 sends the same events to the
    ``sp_analytics_record`` stored procedure, which enforces the identical
    allowlist a second time — this time in the database, where application code
    cannot bypass it.
    """

    def __init__(self) -> None:
        """Create an empty analytics store."""
        self._events: list[AnalyticsEvent] = []
        # The pseudonym mapping. In production this is one encrypted column, so
        # that destroying a user's key destroys the link automatically.
        self._pseudonyms: dict[UUID, UUID] = {}
        self._aggregates: Counter[str] = Counter()

    def analytics_id_for(self, user_id: UUID) -> UUID:
        """Get or create the pseudonym for a user.

        Args:
            user_id: The real account identifier.

        Returns:
            A random identifier unrelated to ``user_id``. Generated on first
            use and remembered thereafter.
        """
        existing = self._pseudonyms.get(user_id)
        if existing is None:
            existing = uuid4()
            self._pseudonyms[user_id] = existing
        return existing

    def sever(self, user_id: UUID) -> None:
        """Break the link between a user and their analytics, permanently.

        Called during account deletion. The events themselves are untouched and
        keep contributing to the totals — but nothing can ever attribute them
        to a person again.

        Args:
            user_id: Whose link to sever.
        """
        self._pseudonyms.pop(user_id, None)

    def record(
        self,
        user_id: UUID,
        event_name: str,
        *,
        country_code: str | None = None,
        duration_seconds: float | None = None,
        turn_count: int | None = None,
        feature: str | None = None,
        error_category: str | None = None,
        success: bool | None = None,
    ) -> None:
        """Record one event, after checking every field against the allowlist.

        Args:
            user_id: Whose action this was. Converted to a pseudonym
                immediately; the real identifier is not stored on the event.
            event_name: Must be in ``ALLOWED_EVENTS``.
            country_code: Two-letter country code, supplied by Cloudflare.
            duration_seconds: Bucketed before storage, never stored exactly.
            turn_count: A plain count.
            feature: Must be in ``ALLOWED_FEATURES`` if given.
            error_category: Must be in ``ALLOWED_ERROR_CATEGORIES`` if given.
            success: A boolean outcome.

        Raises:
            AnalyticsRejected: If any value is not on its allowlist.
        """
        if event_name not in ALLOWED_EVENTS:
            raise AnalyticsRejected(
                f"'{event_name}' is not a declared analytics event. Add it to "
                "ALLOWED_EVENTS here and to the ENUM in the database migration, in the "
                "same commit — and check first that it reveals nothing about a person."
            )
        if feature is not None and feature not in ALLOWED_FEATURES:
            raise AnalyticsRejected(f"'{feature}' is not a declared feature name.")
        if error_category is not None and error_category not in ALLOWED_ERROR_CATEGORIES:
            raise AnalyticsRejected(f"'{error_category}' is not a declared error category.")
        if country_code is not None and (len(country_code) != 2 or not country_code.isalpha()):
            raise AnalyticsRejected("Country must be a two-letter code, or omitted.")

        event = AnalyticsEvent(
            analytics_id=self.analytics_id_for(user_id),
            event_name=event_name,
            country_code=country_code.upper() if country_code else None,
            duration_bucket=bucket_duration(duration_seconds) if duration_seconds is not None else None,
            turn_count=turn_count,
            feature=feature,
            error_category=error_category,
            success=success,
        )
        self._events.append(event)

        # Aggregates are updated as events arrive. They are computed nightly in
        # production, for one reason worth understanding: aggregates outlive
        # the raw events they came from, and cannot be recomputed after users
        # are deleted. Collect them early or lose them forever.
        self._aggregates[event_name] += 1
        if event.country_code:
            self._aggregates[f"country:{event.country_code}"] += 1

        _log.debug("analytics_recorded", event_name=event_name, feature=feature)

    def snapshot(self) -> dict[str, int]:
        """Return the current aggregate counters.

        Returns:
            A mapping of counter name to value. Contains no identifiers of any
            kind — safe to display, log, or put on a dashboard.
        """
        return dict(self._aggregates)

    @staticmethod
    def country_from_headers(headers: dict[str, str]) -> str | None:
        """Read the visitor's country from the edge network's header.

        In production Cloudflare sits in front of the API and adds
        ``CF-IPCountry``. Taking the country from there means this server never
        inspects, stores, or looks up an IP address to obtain geography — the
        address is used by Cloudflare and discarded before it reaches us.

        Args:
            headers: The incoming request headers, lowercased.

        Returns:
            A two-letter country code, or ``None`` locally where no edge
            network is present.
        """
        value = headers.get("cf-ipcountry") or headers.get("x-country")
        if value and len(value) == 2 and value.isalpha() and value.upper() != "XX":
            return value.upper()
        return None
