"""Shared response shapes used across the whole API.

WHAT A PYDANTIC MODEL IS AND WHY EVERY ENDPOINT HAS ONE
Pydantic is a library for declaring the exact shape of data. A model says "this
request must contain a string called `message` between 1 and 4000 characters".
Three things follow from that single declaration:

1. **Validation.** Anything that does not match is rejected before a line of
   our code runs. This is the input-validation layer, and it is not optional
   or bolted on — it is a consequence of describing the data properly.
2. **Documentation.** FastAPI reads these models and generates the Swagger page
   at `/docs`. The documentation cannot drift from reality because it is
   produced from the same declaration that enforces it.
3. **Type safety.** Editors and the type checker know what fields exist.

A RULE ABOUT EXAMPLES
Every example value in this file and its siblings is invented. No real email
address, no real name, no real transcript. Swagger examples are published to
anyone who can reach `/docs`, and test fixtures get copied into bug reports —
both are ways real data escapes if you let it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base class for every model in the API.

    Sets one shared behaviour: unknown fields in an incoming request are
    rejected rather than quietly ignored. That turns a typo like ``mesage``
    into an immediate, obvious error instead of a message that silently
    vanishes — and it stops a caller smuggling extra fields into a request that
    later code might pick up.
    """

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(ApiModel):
    """The contents of an error response."""

    code: str = Field(
        description=(
            "A short, stable, machine-readable code. Branch on this in the frontend "
            "rather than on the message text, which may be reworded at any time."
        ),
        examples=["rate_limited"],
    )
    message: str = Field(
        description="A plain-language explanation, safe to show the user. Never contains personal data.",
        examples=["Too many requests. Please wait 42 seconds and try again."],
    )
    correlation_id: str = Field(
        description=(
            "The identifier for this request. Quote it when reporting a problem — it is "
            "how the whole request can be traced in the logs without anyone reading "
            "your account data."
        ),
        examples=["3f1c9a7e-0b52-4d18-9a3e-77c0f1a2b8d4"],
    )


class ErrorResponse(ApiModel):
    """The standard error body returned by every failing endpoint."""

    error: ErrorDetail


class Page[ItemT](ApiModel):
    """One page of a list of results.

    Paging exists here for a privacy reason as well as a performance one: every
    item returned costs a decryption, so unbounded lists would be both slow and
    a way to make the server decrypt everything at once.
    """

    items: list[ItemT] = Field(description="The results on this page.")
    total: int = Field(description="How many results exist in total.", examples=[3])
    limit: int = Field(description="How many were requested.", examples=[50])
    offset: int = Field(description="How many were skipped.", examples=[0])


class Acknowledgement(ApiModel):
    """A simple confirmation for actions that return no data."""

    ok: bool = Field(default=True, description="Always true when the action succeeded.")
    detail: str = Field(description="What happened, in plain language.", examples=["Signed out."])
