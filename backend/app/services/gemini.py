"""The Google Gemini client: the only code that talks to the AI.

WHY THIS IS HAND-WRITTEN RATHER THAN USING GOOGLE'S SDK
Google publishes a Python library for Gemini, and it would be fewer lines. It
was not used, for one reason that matters: it opens its own network
connections, which would travel around the SSRF guard in
`app/core/security/ssrf.py`. Every outbound request from this server goes
through that guard — a rule with no exceptions is enforceable, and a rule with
one exception is not. Calling the REST interface directly with our own checked
client keeps the rule intact, and as a bonus gives full control over retries,
timeouts, and exactly what gets logged.

WHAT IS LOGGED, AND WHAT IS NOT
Per call: the model, how long it took, tokens in and out, why generation
stopped, whether a safety filter fired, any error code, and how many retries
were needed. **Never the prompt and never the response.** Those are the
player's words, and they are personal data.

There is one exception, and it is not silent: a player can switch on "help us
debug this session", which stores the prompt and response encrypted under their
own key for at most 48 hours, readable only through the audited support flow.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.core.errors import QuotaExhaustedError, UpstreamAiError
from app.core.logging import get_logger
from app.core.security.ssrf import SafeHttpClient, SsrfBlockedError, SsrfGuard

_log = get_logger("gemini")

# Only these HTTP statuses are worth trying again. A 400 means our request was
# malformed and will be malformed the second time too; retrying it just wastes
# quota and delays the error the developer needs to see.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class GeminiResult:
    """One successful reply from the model.

    Attributes:
        text: The generated narration.
        tokens_in: Tokens consumed by the prompt.
        tokens_out: Tokens produced in the reply.
        finish_reason: Why generation stopped. ``STOP`` is normal completion.
        latency_ms: Round-trip duration.
        model_id: Which model answered.
        retry_count: How many attempts were needed beyond the first.
    """

    text: str
    tokens_in: int
    tokens_out: int
    finish_reason: str
    latency_ms: int
    model_id: str
    retry_count: int


class GeminiClient:
    """Sends prompts to Gemini and turns its replies into something usable."""

    def __init__(self, settings: Settings) -> None:
        """Set up the client.

        Args:
            settings: Application settings, supplying the API key, the model,
                the base address, and the timeout. The SSRF allowlist is
                derived from the same base address, so the client and its guard
                cannot disagree about where Gemini is.
        """
        self._settings = settings
        self._http = SafeHttpClient(
            SsrfGuard(settings.outbound_allowed_hosts),
            timeout=settings.gemini_timeout_seconds,
        )

    async def generate(
        self,
        *,
        system_instruction: str,
        contents: list[dict[str, Any]],
        max_output_tokens: int = 1024,
        temperature: float = 0.9,
    ) -> GeminiResult:
        """Ask the model for a reply, retrying temporary failures.

        Args:
            system_instruction: The standing instruction shaping the model's
                behaviour — here, the Dungeon Master's brief.
            contents: The conversation so far, in Gemini's format.
            max_output_tokens: A ceiling on the reply length. This is a cost
                control as much as a style one: it is the hard limit on how
                much of the free allowance one turn can consume.
            temperature: How varied the output is. 0.9 suits storytelling,
                where the same input twice should not produce identical prose.
                A lower value would suit extraction or classification.

        Returns:
            The generated text and the metrics for the call.

        Raises:
            QuotaExhaustedError: If the free tier's allowance is used up.
            UpstreamAiError: For any other failure, including a safety block.
        """
        url = (
            f"{self._settings.gemini_base_url.rstrip('/')}"
            f"/v1beta/models/{self._settings.gemini_model_id}:generateContent"
        )
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "topP": 0.95,
            },
        }
        headers = {
            # The key travels in a header, never in the URL. Anything in a URL
            # ends up in server access logs, browser history and proxy logs;
            # a header does not.
            "x-goog-api-key": self._settings.gemini_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        last_error: str = "unknown"

        for attempt in range(self._settings.gemini_max_retries + 1):
            try:
                response = await self._http.post_json(url, json_body=body, headers=headers)
            except SsrfBlockedError as exc:
                # Never retried. A blocked destination is a configuration fault
                # or an attack, and neither improves by trying again.
                _log.error("gemini_blocked_by_ssrf_guard", reason_code="ssrf_blocked")
                raise UpstreamAiError(
                    "The AI service address was refused by this server's outbound "
                    "safety checks. This is a configuration problem, not a network fault.",
                    code="ssrf_blocked",
                ) from exc
            except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
                # Could not establish a connection at all. Not retried: if the
                # host is unreachable now it will be unreachable a second
                # later, and three attempts would only make the player wait
                # three times as long for the same answer.
                _log.warning("gemini_unreachable", error_code="connect_failed", attempt=attempt)
                raise UpstreamAiError(
                    "Could not reach the AI service. Check your internet connection, and "
                    "that GEMINI_BASE_URL in the backend configuration is correct.",
                    code="upstream_unreachable",
                ) from exc
            except httpx.TimeoutException:
                # The connection was accepted but no reply arrived in time.
                #
                # NOT RETRIED, deliberately. A timeout has already consumed the
                # entire waiting budget, so retrying it twice more turns a
                # 30-second failure into a 95-second one — and a player who has
                # stared at a spinner for a minute and a half would much rather
                # have been told at 30 seconds. Genuinely transient faults
                # surface as 5xx responses, which ARE retried below.
                _log.warning(
                    "gemini_timeout",
                    attempt=attempt,
                    model_id=self._settings.gemini_model_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                raise UpstreamAiError(
                    "The Dungeon Master took too long to answer. Please try again.",
                    code="upstream_timeout",
                ) from None
            except httpx.HTTPError as exc:
                last_error = "network"
                if await self._maybe_wait(attempt):
                    continue
                _log.warning("gemini_network_error", attempt=attempt)
                raise UpstreamAiError(
                    "Could not reach the AI service. Check your internet connection.",
                    code="upstream_unreachable",
                ) from exc

            if response.status_code == 200:
                latency_ms = int((time.perf_counter() - started) * 1000)
                return self._parse(response.json(), latency_ms=latency_ms, retry_count=attempt)

            if response.status_code in RETRYABLE_STATUSES:
                last_error = str(response.status_code)
                if response.status_code == 429 and attempt >= self._settings.gemini_max_retries:
                    _log.warning(
                        "gemini_quota_exhausted",
                        error_code="RESOURCE_EXHAUSTED",
                        model_id=self._settings.gemini_model_id,
                        retry_count=attempt,
                    )
                    raise QuotaExhaustedError()
                if await self._maybe_wait(attempt):
                    continue

            self._raise_for_status(response, attempt)

        raise UpstreamAiError(
            f"The AI service did not respond successfully ({last_error}).",
            code="upstream_ai_error",
        )

    async def _maybe_wait(self, attempt: int) -> bool:
        """Pause before retrying, if any retries remain.

        Uses exponential backoff with jitter. Backoff means each wait is longer
        than the last, so a struggling service is given room to recover rather
        than being hammered. Jitter is a small random variation, which stops
        many clients that failed at the same moment from all retrying in
        lockstep and recreating the overload they are recovering from.

        Args:
            attempt: Which attempt has just failed, counting from zero.

        Returns:
            True if the caller should try again; False if attempts are spent.
        """
        if attempt >= self._settings.gemini_max_retries:
            return False
        delay = (2**attempt) + random.uniform(0, 0.5)  # noqa: S311 - jitter, not cryptography
        await asyncio.sleep(delay)
        return True

    def _raise_for_status(self, response: httpx.Response, attempt: int) -> None:
        """Turn a failed HTTP response into a clear application error.

        Args:
            response: The failed response.
            attempt: How many attempts had been made.

        Raises:
            QuotaExhaustedError: On 429, the free tier's allowance.
            UpstreamAiError: On anything else.
        """
        code = self._extract_error_code(response)
        _log.warning(
            "gemini_error_response",
            status_code=response.status_code,
            error_code=code,
            model_id=self._settings.gemini_model_id,
            retry_count=attempt,
        )
        if response.status_code == 429:
            raise QuotaExhaustedError()
        if response.status_code in (401, 403):
            raise UpstreamAiError(
                "The AI service rejected our credentials. The GEMINI_API_KEY is missing, "
                "wrong, or has not been enabled for this model.",
                code="upstream_auth_failed",
            )
        if response.status_code == 404:
            raise UpstreamAiError(
                f"The model '{self._settings.gemini_model_id}' was not found. Run "
                "'uv run python scripts/check_gemini_models.py' to list the models your "
                "key can actually use.",
                code="model_not_found",
            )
        raise UpstreamAiError(
            "The AI service returned an error. Please try again in a moment.",
            code="upstream_ai_error",
        )

    @staticmethod
    def _extract_error_code(response: httpx.Response) -> str:
        """Pull the machine-readable error code out of a failed response.

        Deliberately takes only the ``status`` field, never the human-readable
        message. Provider error messages sometimes quote the offending request
        back — which would put the player's words into our logs.

        Args:
            response: The failed response.

        Returns:
            A short code such as ``RESOURCE_EXHAUSTED``, or ``"unknown"``.
        """
        try:
            payload = response.json()
            return str(payload.get("error", {}).get("status", "unknown"))
        except Exception:  # noqa: BLE001 - a malformed error body is not itself an error
            return "unknown"

    def _parse(self, payload: dict[str, Any], *, latency_ms: int, retry_count: int) -> GeminiResult:
        """Turn a successful response body into a result object.

        Args:
            payload: The decoded JSON response.
            latency_ms: How long the call took.
            retry_count: How many retries were needed.

        Returns:
            The parsed result.

        Raises:
            UpstreamAiError: If the model returned no usable text — most often
                because a safety filter stopped it.
        """
        candidates = payload.get("candidates") or []
        usage = payload.get("usageMetadata") or {}
        tokens_in = int(usage.get("promptTokenCount", 0))
        tokens_out = int(usage.get("candidatesTokenCount", 0))

        if not candidates:
            # No candidates at all usually means the *prompt* was blocked
            # before generation started.
            _log.warning("gemini_no_candidates", safety_blocked=True, tokens_in=tokens_in)
            raise UpstreamAiError(
                "The Dungeon Master could not respond to that. Try rephrasing it.",
                code="content_blocked",
            )

        candidate = candidates[0]
        finish_reason = str(candidate.get("finishReason", "STOP"))
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()

        if not text:
            _log.warning(
                "gemini_empty_reply",
                finish_reason=finish_reason,
                safety_blocked=finish_reason == "SAFETY",
                tokens_in=tokens_in,
            )
            if finish_reason == "SAFETY":
                raise UpstreamAiError(
                    "The Dungeon Master declined to narrate that. Try a different approach.",
                    code="content_blocked",
                )
            raise UpstreamAiError(
                "The Dungeon Master returned an empty reply. Please try again.",
                code="empty_response",
            )

        # This is the observability record required for every AI call. Note
        # what is present — metrics — and what is absent: the prompt and the
        # reply. Only their lengths are recorded.
        _log.info(
            "gemini_call_completed",
            model_id=self._settings.gemini_model_id,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            finish_reason=finish_reason,
            safety_blocked=finish_reason == "SAFETY",
            retry_count=retry_count,
            response_chars=len(text),
            estimated_cost_micros=0,  # zero on the free tier
        )

        return GeminiResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            model_id=self._settings.gemini_model_id,
            retry_count=retry_count,
        )

    async def aclose(self) -> None:
        """Close network connections when the application shuts down."""
        await self._http.aclose()
