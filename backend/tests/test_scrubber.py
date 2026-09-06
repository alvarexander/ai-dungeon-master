"""Tests for the outbound personal data scrubber.

The scrubber runs on prompts before they leave for Google, whose free tier
terms permit them to use submitted content for product improvement and state
that human reviewers may read it.
"""

from __future__ import annotations

import pytest

from app.services.scrubber import scrub


@pytest.mark.parametrize(
    ("text", "must_not_contain"),
    [
        ("Email me at wren@example.com about it", "wren@example.com"),
        ("Call me on +44 7700 900123 tonight", "7700"),
        ("My card is 4111 1111 1111 1111", "4111"),
        ("I live at SW1A 1AA", "SW1A"),
        ("See https://example.com/u/12345 for details", "12345"),
        ("Born 14/07/1987 in the north", "1987"),
    ],
)
def test_structured_personal_data_is_removed(text, must_not_contain):
    """Anything with a recognisable shape is stripped before it is sent."""
    result = scrub(text)
    assert must_not_contain not in result.text
    assert result.changed


def test_ordinary_play_is_left_alone():
    """The scrubber must not damage the game.

    An early version stripped every capitalised word and made the Dungeon
    Master incoherent. A privacy control that ruins the product gets switched
    off, and a control that is switched off protects nobody.
    """
    text = "I push open the chapel door and hold up the lantern, calling out for Brother Aldwin."
    result = scrub(text)

    assert result.text == text
    assert not result.changed


def test_character_names_survive():
    """Proper nouns are preserved, because they are usually fictional."""
    text = "Wren Ashdown draws her blade and steps between Marisol and the doorway."
    assert scrub(text).text == text


def test_the_placeholder_keeps_the_sentence_meaningful():
    """The model still understands what kind of thing was mentioned.

    Replacing an address with '[an email address]' rather than deleting it
    keeps the narration coherent while the address itself never leaves.
    """
    result = scrub("The note reads: contact wren@example.com")
    assert "[an email address]" in result.text
    assert result.replacements == 1


def test_multiple_items_are_all_removed_and_counted():
    """Every match is replaced, and the count is reported."""
    result = scrub("Reach me at a@example.com or b@example.com")
    assert "@example.com" not in result.text
    assert result.replacements == 2
