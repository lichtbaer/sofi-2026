"""Auswertung der Wolkenfelder: Punktabfrage und Kartenoverlay."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import Settings, get_settings
from ..db import connection
from ..eclipse import local_circumstances
from ..grib2 import LatLonGrid
from .icon_d2 import MODEL, NODATA

#: Wie stark eine Wolkenschicht die tiefstehende Sonne verdeckt. Bei 2–7° Höhe
#: ist der Lichtweg zehn- bis zwanzigfach länger als im Zenit, deshalb dämpfen
#: selbst hohe Zirren spürbar — aber die Sichel bleibt sichtbar. Tiefe
#: Bewölkung beendet die Beobachtung. Heuristik, keine Strahlungsrechnung.
_LAYER_OPACITY = {"low": 1.0, "mid": 0.85, "high": 0.45}


@dataclass(frozen=True, slots=True)
class Field:
    variable: str
    valid_at: datetime
    path: Path
    grid: LatLonGrid
    run_at: datetime
    model: str


@dataclass(frozen=True, slots=True)
class CloudSample:
    valid_at: datetime
    total: float | None
    low: float | None
    mid: float | None
    high: float | None

    @property
    def obstruction(self) -> float | None:
        """Anteil der verdeckten Sicht auf die tiefstehende Sonne, 0…1."""
        if self.low is None or self.mid is None or self.high is None:
            return None
        clear = 1.0
        for layer, value in (("low", self.low), ("mid", self.mid), ("high", self.high)):
            clear *= 1.0 - _LAYER_OPACITY[layer] * value
        return 1.0 - clear


@dataclass(frozen=True, slots=True)
class PointForecast:
    model: str
    run_at: datetime
    maximum_at: datetime
    at_maximum: CloudSample
    series: list[CloudSample]


async def current_fields(settings: Settings | None = None) -> list[Field]:
    """Alle Felder des jüngsten abgeschlossenen Laufs."""
    settings = settings or get_settings()
    async with connection() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT variable, valid_at, path, ni, nj, lat_first, lon_first, dlat, dlon,
                       model, run_at
                FROM forecast_field_current
                WHERE model = %s
                ORDER BY valid_at, variable
                """,
                (MODEL,),
            )
        ).fetchall()

    return [
        Field(
            variable=r["variable"],
            valid_at=r["valid_at"],
            path=Path(r["path"]),
            grid=LatLonGrid(
                ni=r["ni"],
                nj=r["nj"],
                lat_first=r["lat_first"],
                lon_first=r["lon_first"],
                dlat=r["dlat"],
                dlon=r["dlon"],
            ),
            run_at=r["run_at"],
            model=r["model"],
        )
        for r in rows
    ]


@lru_cache(maxsize=64)
def _load(path: str, mtime_ns: int) -> np.ndarray:
    """Feld als memmap. ``mtime_ns`` invalidiert den Cache bei neuem Lauf."""
    del mtime_ns
    return np.load(path, mmap_mode="r")


def load(field: Field) -> np.ndarray:
    return _load(str(field.path), field.path.stat().st_mtime_ns)


def sample(field: Field, lat: float, lon: float) -> float | None:
    """Bewölkungsgrad 0…1 am Punkt, bilinear. ``None`` außerhalb der Domäne."""
    grid = field.grid
    if not grid.contains(lat, lon):
        return None

    fj, fi = grid.fractional_index(lat, lon)
    j0, i0 = int(fj), int(fi)
    j1, i1 = min(j0 + 1, grid.nj - 1), min(i0 + 1, grid.ni - 1)
    wj, wi = fj - j0, fi - i0

    data = load(field)
    window = np.array(
        [data[j0, i0], data[j0, i1], data[j1, i0], data[j1, i1]], dtype=np.float64
    )
    weights = np.array([(1 - wj) * (1 - wi), (1 - wj) * wi, wj * (1 - wi), wj * wi])

    valid = window != NODATA
    if not valid.any():
        return None
    weights = np.where(valid, weights, 0.0)
    total = weights.sum()
    if total <= 0:
        return None
    return float((np.where(valid, window, 0.0) @ weights) / total / 100.0)


def _interpolate(before: CloudSample, after: CloudSample, at: datetime) -> CloudSample:
    span = (after.valid_at - before.valid_at).total_seconds()
    f = 0.0 if span <= 0 else (at - before.valid_at).total_seconds() / span

    def mix(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else a + (b - a) * f

    return CloudSample(
        valid_at=at,
        total=mix(before.total, after.total),
        low=mix(before.low, after.low),
        mid=mix(before.mid, after.mid),
        high=mix(before.high, after.high),
    )


async def point_forecast(lat: float, lon: float) -> PointForecast | None:
    """Wolkenprognose für einen Ort, ausgewertet zur *lokalen* Maximumszeit."""
    fields = await current_fields()
    if not fields:
        return None

    by_time: dict[datetime, dict[str, Field]] = {}
    for field in fields:
        by_time.setdefault(field.valid_at, {})[field.variable] = field

    series = [
        CloudSample(
            valid_at=valid_at,
            total=sample(group["clct"], lat, lon) if "clct" in group else None,
            low=sample(group["clcl"], lat, lon) if "clcl" in group else None,
            mid=sample(group["clcm"], lat, lon) if "clcm" in group else None,
            high=sample(group["clch"], lat, lon) if "clch" in group else None,
        )
        for valid_at, group in sorted(by_time.items())
    ]
    if all(s.total is None for s in series):
        return None

    circumstances = local_circumstances(lat, lon)
    maximum_at = circumstances.maximum.time

    before = max((s for s in series if s.valid_at <= maximum_at), key=lambda s: s.valid_at, default=None)
    after = min((s for s in series if s.valid_at >= maximum_at), key=lambda s: s.valid_at, default=None)
    if before is None:
        at_maximum = after
    elif after is None or before is after:
        at_maximum = before
    else:
        at_maximum = _interpolate(before, after, maximum_at)

    return PointForecast(
        model=fields[0].model,
        run_at=fields[0].run_at,
        maximum_at=maximum_at,
        at_maximum=at_maximum,
        series=series,
    )


def render_overlay(field: Field, bbox: tuple[float, float, float, float]) -> tuple[bytes, tuple[float, float, float, float]]:
    """PNG des Feldes für den Kartenüberlagerung.

    Der Graukanal trägt den Bewölkungsgrad direkt in Prozent (0…100), der
    Alphakanal ist 0 wo keine Daten vorliegen. Die Farbgebung macht das
    Frontend — so bleibt die Farbwahl im Design und nicht im Backend.
    Rückgabe: PNG-Bytes und die tatsächlich getroffenen Grenzen.
    """
    grid = field.grid
    lat_min, lon_min, lat_max, lon_max = bbox

    def index_range(first: float, delta: float, count: int, lo: float, hi: float) -> tuple[int, int]:
        a = (lo - first) / delta
        b = (hi - first) / delta
        start, end = (a, b) if delta > 0 else (b, a)
        return max(0, int(np.floor(start))), min(count - 1, int(np.ceil(end)))

    j0, j1 = index_range(grid.lat_first, grid.dlat, grid.nj, lat_min, lat_max)
    i0, i1 = index_range(grid.lon_first, grid.dlon, grid.ni, lon_min, lon_max)
    if j0 > j1 or i0 > i1:
        raise ValueError("bbox liegt außerhalb des Modellgebiets")

    window = np.asarray(load(field)[j0 : j1 + 1, i0 : i1 + 1])

    # Bildzeile 0 ist oben; das ICON-Gitter läuft süd→nord.
    if grid.dlat > 0:
        window = window[::-1]
    if grid.dlon < 0:
        window = window[:, ::-1]

    alpha = np.where(window == NODATA, 0, 255).astype(np.uint8)
    grey = np.where(window == NODATA, 0, window).astype(np.uint8)

    buffer = io.BytesIO()
    Image.fromarray(np.dstack([grey, alpha]), mode="LA").save(buffer, format="PNG", optimize=True)

    lat_a = grid.lat_first + grid.dlat * j0
    lat_b = grid.lat_first + grid.dlat * j1
    lon_a = grid.lon_first + grid.dlon * i0
    lon_b = grid.lon_first + grid.dlon * i1
    return buffer.getvalue(), (min(lat_a, lat_b), min(lon_a, lon_b), max(lat_a, lat_b), max(lon_a, lon_b))
