"""Removes things that look like personal data from prompts before they leave.

WHY THIS EXISTS
Every prompt sent to Gemini leaves your infrastructure and arrives on Google's
servers. Google's published terms for the free tier are explicit about what
happens next: content submitted to the unpaid service is used to provide,
improve and develop Google's products, and human reviewers may read, annotate
and process it. Google states that it disconnects the data from your account
first, and advises not to submit sensitive, confidential or personal
information.

Players will not read those terms. They will type their real first name, their
friend's name, sometimes an address, into a game. So the application takes the
advice on their behalf and strips what it can recognise before sending.

WHAT THIS IS AND IS NOT
This is a *reduction*, not a guarantee. It reliably catches structured things —
email addresses, phone numbers, card-shaped digit strings, postcodes — because
those have recognisable shapes. It cannot catch "my sister Emma is coming
over", because that is indistinguishable from a player naming a character.

Claiming otherwise would be worse than not having it, so the limitation is
stated plainly here, in the documentation, and in the in-app disclosure the
user actually sees. The scrubber lowers the volume of accidental disclosure; it
does not close the channel. The only complete answer is the paid tier, whose
terms forbid training on your prompts entirely.

WHY IT DOES NOT TOUCH NAMES
An early version stripped anything capitalised mid-sentence. It removed every
proper noun in the game — the tavern, the villain, the player's own character —
and made the Dungeon Master incoherent. A privacy control that destroys the
product gets switched off, and a control that is switched off protects nobody.
Structured patterns only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each pattern is paired with the placeholder that replaces it. The placeholder
# is deliberately descriptive: the model still understands that *an email
# address* was mentioned, so the narration stays coherent, while the address
# itself never leaves this server.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email addresses.
    (re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[an email address]"),
    # Long digit runs that look like a payment card, with or without spacing.
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[a card number]"),
    # International and national phone numbers.
    (re.compile(r"(?<!\w)\+\d[\d\s().-]{7,}\d(?!\w)"), "[a phone number]"),
    (re.compile(r"(?<!\w)0\d[\d\s().-]{8,}\d(?!\w)"), "[a phone number]"),
    # UK postcodes.
    (re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE), "[a postcode]"),
    # United States social security numbers.
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[a national ID number]"),
    # Web addresses, which frequently carry identifiers in their path.
    (re.compile(r"\bhttps?://\S+", re.IGNORECASE), "[a web link]"),
    # Dates of birth written in full numeric form.
    (re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}\b"), "[a date]"),
]


@dataclass(frozen=True, slots=True)
class ScrubResult:
    """The outcome of scrubbing one piece of text.

    Attributes:
        text: The text with recognised patterns replaced.
        replacements: How many things were replaced. Logged as a count — never
            what they were, which would defeat the purpose entirely.
    """

    text: str
    replacements: int

    @property
    def changed(self) -> bool:
        """Return True if anything was removed."""
        return self.replacements > 0


def scrub(text: str) -> ScrubResult:
    """Replace recognisable personal data in a piece of text.

    Args:
        text: What the player wrote.

    Returns:
        The scrubbed text and a count of replacements. The count is safe to log
        and is surfaced to the frontend so the behaviour is visible to the user
        rather than silent.
    """
    replacements = 0
    scrubbed = text
    for pattern, placeholder in _PATTERNS:
        scrubbed, count = pattern.subn(placeholder, scrubbed)
        replacements += count
    return ScrubResult(text=scrubbed, replacements=replacements)
