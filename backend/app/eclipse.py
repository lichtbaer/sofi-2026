"""Lokale Umstände der Sonnenfinsternis vom 12.08.2026.

Portierung von ``frontend/eclipse.js``. Die Rechnung gehört weiterhin primär in
den Browser — sie ist dort schneller als jeder Roundtrip. Serverseitig brauchen
wir sie trotzdem: die Wolkenprognose wird zur *lokalen* Maximumszeit ausgewertet,
und die Standortbewertung läuft im Batch.

Zwei Implementierungen driften auseinander, wenn niemand hinsieht — deshalb
vergleicht ``tests/test_eclipse.py`` beide gegen dieselben Stützstellen.

Quelle der Besselschen Elemente: NASA/GSFC Five Millennium Canon of Solar
Eclipses (F. Espenak), t0 = 2026 Aug 12, 18.000 TDT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DELTA_T = 75.4  # ΔT in Sekunden
TAN_F1 = 0.0046141
TAN_F2 = 0.0045911

_ELEMENTS: dict[str, tuple[float, float, float, float]] = {
    "x": (0.4755140, 0.5189249, -0.0000773, -0.0000080),
    "y": (0.7711830, -0.2301680, -0.0001246, 0.0000038),
    "d": (14.7966700, -0.0120650, -0.0000030, 0.0),
    "l1": (0.5379550, 0.0000939, -0.0000121, 0.0),
    "l2": (-0.0081420, 0.0000935, -0.0000121, 0.0),
    "mu": (88.747787, 15.003090, 0.0, 0.0),
}

T0 = datetime(2026, 8, 12, 18, 0, 0, tzinfo=UTC)

EARTH_RADIUS_M = 6378140.0
FLATTENING = 0.99664719
#: Sonnenhöhe bei Untergang: Refraktion am Horizont plus Halbmesser.
SUNSET_ALTITUDE = -0.833


def _poly(c: tuple[float, float, float, float], t: float) -> float:
    return c[0] + t * (c[1] + t * (c[2] + t * c[3]))


def time_at(t: float) -> datetime:
    """Rechnet Besselsche Stunden nach t0 (TDT) in Weltzeit um."""
    return T0 + timedelta(seconds=t * 3600.0 - DELTA_T)


@dataclass(frozen=True, slots=True)
class State:
    """Momentaufnahme der Finsternis an einem Ort."""

    t: float
    m: float  # Abstand Schattenachse–Beobachter in Erdradien
    l1: float
    l2: float
    magnitude: float
    obscuration: float  # bedeckter Flächenanteil der Sonnenscheibe, 0…1
    altitude: float  # Sonnenhöhe in Grad
    azimuth: float  # Sonnenazimut in Grad, von Nord über Ost

    @property
    def time(self) -> datetime:
        return time_at(self.t)


@dataclass(frozen=True, slots=True)
class Circumstances:
    visible: bool
    maximum: State
    c1: State | None = None
    c4: State | None = None
    sunset: datetime | None = None
    ends_at_sunset: bool = False


class _Observer:
    """Geozentrische Hilfsgrößen ρ·sin φ' und ρ·cos φ'."""

    __slots__ = ("lat", "lon", "rho_sin", "rho_cos")

    def __init__(self, lat: float, lon: float, height_m: float = 0.0) -> None:
        u = math.atan(FLATTENING * math.tan(math.radians(lat)))
        self.lat = lat
        self.lon = lon
        self.rho_sin = FLATTENING * math.sin(u) + (height_m / EARTH_RADIUS_M) * math.sin(
            math.radians(lat)
        )
        self.rho_cos = math.cos(u) + (height_m / EARTH_RADIUS_M) * math.cos(math.radians(lat))


def _overlap_fraction(d: float, r_sun: float, r_moon: float) -> float:
    """Von zwei Kreisen überdeckter Flächenanteil der Sonnenscheibe."""
    if d >= r_sun + r_moon:
        return 0.0
    if d <= r_moon - r_sun:
        return 1.0
    if d <= r_sun - r_moon:
        return (r_moon * r_moon) / (r_sun * r_sun)
    a = math.acos((d * d + r_sun * r_sun - r_moon * r_moon) / (2 * d * r_sun))
    b = math.acos((d * d + r_moon * r_moon - r_sun * r_sun) / (2 * d * r_moon))
    area = r_sun**2 * (a - math.sin(2 * a) / 2) + r_moon**2 * (b - math.sin(2 * b) / 2)
    return area / (math.pi * r_sun**2)


def _state_at(o: _Observer, t: float) -> State:
    x = _poly(_ELEMENTS["x"], t)
    y = _poly(_ELEMENTS["y"], t)
    d = math.radians(_poly(_ELEMENTS["d"], t))
    l1 = _poly(_ELEMENTS["l1"], t)
    l2 = _poly(_ELEMENTS["l2"], t)
    mu = _poly(_ELEMENTS["mu"], t)

    h = math.radians(mu + o.lon - 0.00417807 * DELTA_T)
    phi = math.radians(o.lat)

    xi = o.rho_cos * math.sin(h)
    eta = o.rho_sin * math.cos(d) - o.rho_cos * math.cos(h) * math.sin(d)
    zeta = o.rho_sin * math.sin(d) + o.rho_cos * math.cos(h) * math.cos(d)

    du, dv = x - xi, y - eta
    m = math.hypot(du, dv)

    big_l1 = l1 - zeta * TAN_F1
    big_l2 = l2 - zeta * TAN_F2
    r_sun = (big_l1 + big_l2) / 2
    r_moon = (big_l1 - big_l2) / 2

    north = -math.cos(d) * math.cos(h) * math.sin(phi) + math.sin(d) * math.cos(phi)
    east = -math.cos(d) * math.sin(h)
    up = math.cos(d) * math.cos(h) * math.cos(phi) + math.sin(d) * math.sin(phi)

    return State(
        t=t,
        m=m,
        l1=big_l1,
        l2=big_l2,
        magnitude=(big_l1 - m) / (big_l1 + big_l2),
        obscuration=_overlap_fraction(m, r_sun, r_moon),
        altitude=math.degrees(math.asin(up)),
        azimuth=(math.degrees(math.atan2(east, north)) + 360.0) % 360.0,
    )


def _bisect(f, a: float, b: float, iterations: int = 46) -> float:
    fa = f(a)
    for _ in range(iterations):
        mid = (a + b) / 2
        fm = f(mid)
        if (fa < 0) == (fm < 0):
            a, fa = mid, fm
        else:
            b = mid
    return (a + b) / 2


def _golden_minimum(o: _Observer, a: float, b: float, iterations: int) -> float:
    """Minimum von m(t) über Ternärsuche — m ist im Intervall unimodal."""
    for _ in range(iterations):
        m1 = a + (b - a) / 3
        m2 = b - (b - a) / 3
        if _state_at(o, m1).m < _state_at(o, m2).m:
            b = m2
        else:
            a = m1
    return (a + b) / 2


def local_circumstances(lat: float, lon: float, height_m: float = 0.0) -> Circumstances:
    """Kontaktzeiten, Maximum und Sonnenuntergang für einen Ort."""
    o = _Observer(lat, lon, height_m)

    coarse = min((_state_at(o, t / 60.0) for t in range(-180, 181)), key=lambda s: s.m)
    maximum = _state_at(o, _golden_minimum(o, coarse.t - 1 / 60, coarse.t + 1 / 60, 60))

    if maximum.obscuration <= 0.0:
        return Circumstances(visible=False, maximum=maximum)

    def gap(t: float) -> float:
        s = _state_at(o, t)
        return s.m - s.l1

    c1 = _state_at(o, _bisect(gap, maximum.t - 3.0, maximum.t))
    c4 = _state_at(o, _bisect(gap, maximum.t + 3.0, maximum.t))

    sunset: datetime | None = None
    step = 1 / 60
    t = maximum.t
    while t <= maximum.t + 6.0:
        if _state_at(o, t).altitude < SUNSET_ALTITUDE:
            root = _bisect(lambda x: _state_at(o, x).altitude - SUNSET_ALTITUDE, t - step, t)
            sunset = time_at(root)
            break
        t += step

    return Circumstances(
        visible=True,
        maximum=maximum,
        c1=c1,
        c4=c4,
        sunset=sunset,
        ends_at_sunset=sunset is not None and sunset < c4.time,
    )


def max_obscuration(lat: float, lon: float) -> float:
    """Nur der maximale Bedeckungsgrad — für Rasterläufe."""
    o = _Observer(lat, lon, 0.0)
    return _state_at(o, _golden_minimum(o, -2.5, 2.5, 70)).obscuration
