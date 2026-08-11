"""Normalisierung von Ortsnamen für die Suche.

Eigenes Modul ohne Datenbank- oder HTTP-Abhängigkeiten: dieselbe Funktion
erzeugt die Schlüssel beim Seeden und beim Suchen, und sie muss ohne laufenden
Dienst testbar sein.
"""

from __future__ import annotations

import unicodedata

#: Deutsche Umschrift. Erst ersetzen, dann die restlichen Diakritika entfernen —
#: sonst wird aus „ü" ein „u", bevor „ue" entstehen kann.
_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _strip_marks(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_keys(value: str) -> tuple[str, str]:
    """(Schlüssel ohne Diakritika, Schlüssel mit deutscher Umschrift).

    „München" ergibt ``("munchen", "muenchen")`` — damit findet sowohl
    „Munchen" als auch „Muenchen" den Ort.
    """
    lowered = value.strip().lower().replace("ß", "ss")
    plain = _strip_marks(lowered)
    transliterated = _strip_marks(lowered.translate(_TRANSLITERATION))
    return plain, transliterated
