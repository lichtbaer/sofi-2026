"""Normalisierung der Suchschlüssel.

Dieselbe Funktion erzeugt die Schlüssel beim Seeden und beim Suchen — weicht
eine Seite ab, findet die Suche stillschweigend nichts mehr.
"""

from __future__ import annotations

import pytest

from app.normalize import search_keys


@pytest.mark.parametrize(
    ("value", "plain", "transliterated"),
    [
        ("München", "munchen", "muenchen"),
        ("Köln", "koln", "koeln"),
        ("Nürnberg", "nurnberg", "nuernberg"),
        ("Düsseldorf", "dusseldorf", "duesseldorf"),
        ("Gießen", "giessen", "giessen"),
        ("Osnabrück", "osnabruck", "osnabrueck"),
        ("Frankfurt am Main", "frankfurt am main", "frankfurt am main"),
        ("  Kassel  ", "kassel", "kassel"),
        ("SYLT", "sylt", "sylt"),
    ],
)
def test_umlauts_produce_both_spellings(value: str, plain: str, transliterated: str) -> None:
    assert search_keys(value) == (plain, transliterated)


def test_query_spellings_meet_the_stored_keys() -> None:
    """Wie der Nutzer „München" auch tippt — ein Schlüssel muss treffen."""
    stored_plain, stored_alt = search_keys("München")

    for typed in ("München", "münchen", "MÜNCHEN", "Munchen", "Muenchen", "muenchen"):
        plain, alt = search_keys(typed)
        assert plain == stored_plain or alt == stored_alt, typed


def test_empty_input_yields_empty_keys() -> None:
    assert search_keys("   ") == ("", "")
