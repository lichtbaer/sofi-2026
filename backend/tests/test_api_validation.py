"""Eingabevalidierung an den Rändern der API.

Beide Fälle stammen aus dem Sicherheits-Audit: LIKE-Metazeichen in der
Ortssuche erzwangen einen Vollscan pro Anfrage, und ``bbox=inf`` lief bis in
die Fensterrechnung und endete dort als 500er.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes import _parse_bbox
from app.services.geocode import _like_prefix


# ── LIKE-Muster der Ortssuche ───────────────────────────────────────────────

@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        ("kassel", "kassel%"),
        ("%", r"\%%"),
        ("_a", r"\_a%"),
        ("mun%chen", r"mun\%chen%"),
        ("a\\b", "a\\\\b%"),
    ],
)
def test_like_prefix_escapes_metacharacters(value: str, pattern: str) -> None:
    assert _like_prefix(value) == pattern


def test_like_prefix_keeps_plain_text_untouched() -> None:
    """Normale Ortsnamen und PLZs bleiben unverändert — nur '%' angehängt."""
    for value in ("frankfurt am main", "34117", "st. peter-ording"):
        assert _like_prefix(value) == value + "%"


# ── bbox des Kartenoverlays ─────────────────────────────────────────────────

def test_parse_bbox_accepts_germany() -> None:
    assert _parse_bbox("47.0,5.6,55.3,15.4") == (47.0, 5.6, 55.3, 15.4)


@pytest.mark.parametrize(
    "bbox",
    [
        "kaputt",                    # nicht numerisch
        "1,2,3",                     # zu wenige Werte
        "1,2,3,4,5",                 # zu viele Werte
        "inf,5.6,55.3,15.4",         # int(inf) wäre ein OverflowError → 500
        "nan,5.6,55.3,15.4",         # NaN besteht keinen Vergleich
        "55.3,5.6,47.0,15.4",        # lat_min > lat_max
        "47.0,15.4,55.3,5.6",        # lon_min > lon_max
        "91,5.6,95,15.4",            # außerhalb ±90
        "47.0,-181,55.3,15.4",       # außerhalb ±180
    ],
)
def test_parse_bbox_rejects_bad_input_with_400(bbox: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _parse_bbox(bbox)
    assert exc.value.status_code == 400
