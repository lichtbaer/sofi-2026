"""Der Python-Port muss mit frontend/eclipse.js übereinstimmen.

Zwei Implementierungen derselben Rechnung driften auseinander, sobald niemand
hinsieht. Die Referenzwerte stammen aus dem JavaScript und werden mit
``node backend/scripts/golden_eclipse.mjs`` neu erzeugt.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.eclipse import local_circumstances, max_obscuration

GOLDEN = json.loads((Path(__file__).parent / "golden_eclipse.json").read_text())
CASES = GOLDEN["cases"]
IDS = [c["name"] for c in CASES]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_maximum_matches_javascript(case: dict) -> None:
    result = local_circumstances(case["lat"], case["lon"])
    assert result.visible is case["visible"]

    expected = case["maximum"]
    delta = abs((result.maximum.time - _parse(expected["time"])).total_seconds())
    assert delta < 0.5, f"Maximum weicht um {delta:.2f} s ab"
    assert result.maximum.altitude == pytest.approx(expected["altitude"], abs=1e-4)
    assert result.maximum.azimuth == pytest.approx(expected["azimuth"], abs=1e-4)
    assert result.maximum.obscuration == pytest.approx(expected["obscuration"], abs=1e-6)
    assert result.maximum.magnitude == pytest.approx(expected["magnitude"], abs=1e-6)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_contacts_and_sunset_match_javascript(case: dict) -> None:
    result = local_circumstances(case["lat"], case["lon"])

    for key, contact in (("c1", result.c1), ("c4", result.c4)):
        assert contact is not None
        expected = case[key]
        delta = abs((contact.time - _parse(expected["time"])).total_seconds())
        assert delta < 0.5, f"{key} weicht um {delta:.2f} s ab"
        assert contact.altitude == pytest.approx(expected["altitude"], abs=1e-4)

    if case["sunset"] is None:
        assert result.sunset is None
    else:
        assert result.sunset is not None
        # Der Untergang wird in Minutenschritten gesucht, danach halbiert —
        # eine Sekunde Toleranz deckt die abweichende Schrittfolge ab.
        assert abs((result.sunset - _parse(case["sunset"])).total_seconds()) < 1.0
    assert result.ends_at_sunset is case["endsAtSunset"]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_max_obscuration_matches_full_computation(case: dict) -> None:
    """Die schnelle Rastervariante darf nicht von der vollen Rechnung abweichen."""
    fast = max_obscuration(case["lat"], case["lon"])
    assert fast == pytest.approx(case["maximum"]["obscuration"], abs=1e-6)


def test_outside_visibility_returns_invisible() -> None:
    # Kapstadt sieht von dieser Finsternis nichts.
    result = local_circumstances(-33.92, 18.42)
    assert result.visible is False
    assert result.c1 is None


def test_altitude_at_maximum_is_low_everywhere_in_germany() -> None:
    """Die fachliche Kernaussage: die Sonne steht im Maximum sehr tief.

    Daran hängt die gesamte Standortbewertung — fiele diese Annahme, wäre die
    Gewichtung der Horizontfreiheit falsch.
    """
    altitudes = [local_circumstances(c["lat"], c["lon"]).maximum.altitude for c in CASES]
    assert max(altitudes) < 10.0
    assert min(altitudes) > 0.0
