"""Strikter GRIB2-Leser für die ICON-D2-Felder von opendata.dwd.de.

Bewusst nur der Ausschnitt, den DWD für ``regular-lat-lon single-level``
liefert: Gitter-Template 3.0, Produkt-Template 4.0, Datendarstellung 5.0
(simple packing) und optionale Bitmap in Sektion 6. Alles andere wirft eine
``Grib2Error``. Ein halb passender Decoder, der stillschweigend falsche Zahlen
liefert, wäre hier schlimmer als gar keiner — eine Wolkenprognose fällt nicht
sofort als falsch auf.

Damit spart sich das Image eccodes und GDAL. Sollte DWD das Packing wechseln,
schlägt der Ingest laut fehl und wir tauschen an genau einer Stelle.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterator

import numpy as np


class Grib2Error(ValueError):
    """GRIB2-Nachricht ist fehlerhaft oder verwendet ein nicht unterstütztes Template."""


# Sektion 4, Oktett 18: Einheit des Vorhersagezeitraums (WMO Code Table 4.4).
_TIME_UNITS: dict[int, timedelta] = {
    0: timedelta(minutes=1),
    1: timedelta(hours=1),
    2: timedelta(days=1),
    13: timedelta(seconds=1),
}


def _sign_magnitude(raw: int, bits: int) -> int:
    """GRIB2 kodiert vorzeichenbehaftete Ganzzahlen als Betrag mit Vorzeichenbit."""
    sign = 1 << (bits - 1)
    return -(raw & (sign - 1)) if raw & sign else raw


def _u32(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off : off + 4], "big")


def _angle(buf: bytes, off: int) -> float:
    """Breite/Länge aus Sektion 3, Einheit 1e-6 Grad."""
    return _sign_magnitude(_u32(buf, off), 32) / 1e6


@dataclass(frozen=True, slots=True)
class LatLonGrid:
    """Reguläres geografisches Gitter.

    ``lat_first``/``lon_first`` gehören zum ersten Punkt der Daten, ``dlat``
    und ``dlon`` sind vorzeichenbehaftet und zeigen in Scan-Richtung. Damit
    entfällt jede Fallunterscheidung beim Sampling.
    """

    ni: int
    nj: int
    lat_first: float
    lon_first: float
    dlat: float
    dlon: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.nj, self.ni

    @property
    def size(self) -> int:
        return self.ni * self.nj

    def bounds(self) -> tuple[float, float, float, float]:
        """(lat_min, lon_min, lat_max, lon_max) der Gittermittelpunkte."""
        lat_a, lat_b = self.lat_first, self.lat_first + self.dlat * (self.nj - 1)
        lon_a, lon_b = self.lon_first, self.lon_first + self.dlon * (self.ni - 1)
        return min(lat_a, lat_b), min(lon_a, lon_b), max(lat_a, lat_b), max(lon_a, lon_b)

    def fractional_index(self, lat: float, lon: float) -> tuple[float, float]:
        """Gleitkomma-Index (j, i) des Punktes — ohne Rundung, für Interpolation."""
        return (lat - self.lat_first) / self.dlat, (lon - self.lon_first) / self.dlon

    def contains(self, lat: float, lon: float) -> bool:
        j, i = self.fractional_index(lat, lon)
        return 0.0 <= j <= self.nj - 1 and 0.0 <= i <= self.ni - 1


@dataclass(frozen=True, slots=True)
class FixedSurface:
    """Bezugsfläche aus Sektion 4. ``type_ == 255`` heißt „nicht angegeben"."""

    type_: int
    value: float | None

    def __str__(self) -> str:
        return "—" if self.value is None else f"Typ {self.type_} @ {self.value:g}"


MISSING_SURFACE = FixedSurface(255, None)


@dataclass(frozen=True, slots=True)
class Grib2Message:
    grid: LatLonGrid
    discipline: int
    parameter_category: int
    parameter_number: int
    first_surface: FixedSurface
    second_surface: FixedSurface
    reference_time: datetime
    forecast_time: timedelta
    values: np.ndarray  # float32, Form (nj, ni), fehlende Punkte als NaN

    @property
    def valid_time(self) -> datetime:
        return self.reference_time + self.forecast_time

    @property
    def signature(self) -> tuple[int, int, int, FixedSurface, FixedSurface]:
        """Vollständige Kennung des Feldes.

        Parameternummer allein genügt beim DWD nicht: tiefe, mittlere und hohe
        Bewölkung tragen alle 0/6/22 und unterscheiden sich einzig über die
        Druckflächen.
        """
        return (
            self.discipline,
            self.parameter_category,
            self.parameter_number,
            self.first_surface,
            self.second_surface,
        )


def _sections(buf: bytes) -> Iterator[tuple[int, bytes]]:
    if len(buf) < 16 or buf[:4] != b"GRIB":
        raise Grib2Error("kein GRIB-Kennsatz")
    if buf[7] != 2:
        raise Grib2Error(f"GRIB-Edition {buf[7]}, erwartet 2")
    total = int.from_bytes(buf[8:16], "big")
    if total > len(buf):
        raise Grib2Error(f"Nachricht abgeschnitten: {len(buf)} von {total} Byte")

    pos = 16
    while pos < total:
        if buf[pos : pos + 4] == b"7777":
            return
        length = _u32(buf, pos)
        if length < 5 or pos + length > total:
            raise Grib2Error(f"unplausible Sektionslänge {length} bei Offset {pos}")
        yield buf[pos + 4], buf[pos : pos + length]
        pos += length
    raise Grib2Error("Endkennung 7777 fehlt")


def _read_grid(sec: bytes) -> LatLonGrid:
    template = int.from_bytes(sec[12:14], "big")
    if template != 0:
        raise Grib2Error(f"Gitter-Template 3.{template} nicht unterstützt (erwartet 3.0)")

    basic_angle = _u32(sec, 38)
    if basic_angle not in (0, 0xFFFFFFFF):
        raise Grib2Error(f"Basiswinkel {basic_angle} — nur die Standardeinheit 1e-6° wird gelesen")

    ni, nj = _u32(sec, 30), _u32(sec, 34)
    lat1, lon1 = _angle(sec, 46), _angle(sec, 50)
    lat2, lon2 = _angle(sec, 55), _angle(sec, 59)
    di, dj = _u32(sec, 63) / 1e6, _u32(sec, 67) / 1e6
    scanning = sec[71]

    if scanning & 0x20:
        raise Grib2Error("Scan-Modus mit j-Richtung zuerst wird nicht unterstützt")
    if ni < 2 or nj < 2:
        raise Grib2Error(f"entartetes Gitter {ni}×{nj}")

    # Bit 1 gesetzt = i läuft ost→west, Bit 2 gesetzt = j läuft süd→nord.
    step_i = -di if scanning & 0x80 else di
    step_j = dj if scanning & 0x40 else -dj

    # Längen kommen bei DWD in 0…360; für uns ist -180…180 handlicher.
    lon1 = lon1 - 360.0 if lon1 > 180.0 else lon1
    lon2 = lon2 - 360.0 if lon2 > 180.0 else lon2

    grid = LatLonGrid(ni=ni, nj=nj, lat_first=lat1, lon_first=lon1, dlat=step_j, dlon=step_i)

    # Gegenprobe: der letzte Gitterpunkt muss auf den angegebenen Eckpunkt fallen.
    for got, want, label in (
        (lat1 + step_j * (nj - 1), lat2, "Breite"),
        (lon1 + step_i * (ni - 1), lon2, "Länge"),
    ):
        if not math.isclose(got, want, abs_tol=1e-4):
            raise Grib2Error(f"{label} inkonsistent: berechnet {got:.6f}, angegeben {want:.6f}")
    return grid


def _read_surface(sec: bytes, offset: int) -> FixedSurface:
    """Bezugsfläche: Typ, Zehnerexponent und skalierter Wert (Sektion 4, ab Oktett 23)."""
    surface_type = sec[offset]
    scale_factor = sec[offset + 1]
    raw = _u32(sec, offset + 2)
    if surface_type == 255 or scale_factor == 255 or raw == 0xFFFFFFFF:
        return FixedSurface(surface_type, None)
    return FixedSurface(surface_type, _sign_magnitude(raw, 32) / 10.0 ** _sign_magnitude(scale_factor, 8))


def _unpack(raw: bytes, nbits: int, count: int) -> np.ndarray:
    if nbits == 0:
        return np.zeros(count, dtype=np.int64)
    if nbits in (8, 16, 32):
        dtype = {8: ">u1", 16: ">u2", 32: ">u4"}[nbits]
        needed = count * nbits // 8
        if len(raw) < needed:
            raise Grib2Error(f"Datensektion zu kurz: {len(raw)} < {needed} Byte")
        return np.frombuffer(raw, dtype=dtype, count=count).astype(np.int64)

    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8))
    if bits.size < count * nbits:
        raise Grib2Error(f"Datensektion zu kurz für {count} Werte à {nbits} bit")
    bits = bits[: count * nbits].reshape(count, nbits).astype(np.int64)
    return bits @ (1 << np.arange(nbits - 1, -1, -1, dtype=np.int64))


def decode(buf: bytes) -> Grib2Message:
    """Dekodiert genau eine GRIB2-Nachricht."""
    grid: LatLonGrid | None = None
    reference_time: datetime | None = None
    forecast_time: timedelta | None = None
    discipline = buf[6] if len(buf) > 6 else 0
    category = number = -1
    first_surface = second_surface = MISSING_SURFACE
    packing: tuple[float, int, int, int, int] | None = None
    bitmap: np.ndarray | None = None
    payload: bytes | None = None

    for num, sec in _sections(buf):
        if num == 1:
            year = int.from_bytes(sec[12:14], "big")
            reference_time = datetime(year, sec[14], sec[15], sec[16], sec[17], sec[18], tzinfo=UTC)

        elif num == 3:
            grid = _read_grid(sec)

        elif num == 4:
            template = int.from_bytes(sec[7:9], "big")
            if template not in (0, 8):
                raise Grib2Error(f"Produkt-Template 4.{template} nicht unterstützt")
            category, number = sec[9], sec[10]
            unit = _TIME_UNITS.get(sec[17])
            if unit is None:
                raise Grib2Error(f"Zeiteinheit {sec[17]} unbekannt")
            forecast_time = unit * _u32(sec, 18)
            if len(sec) >= 34:
                first_surface = _read_surface(sec, 22)
                second_surface = _read_surface(sec, 28)

        elif num == 5:
            npoints = _u32(sec, 5)
            template = int.from_bytes(sec[9:11], "big")
            if template != 0:
                raise Grib2Error(
                    f"Datendarstellung 5.{template} nicht unterstützt — "
                    "dieser Leser kann nur simple packing (5.0)"
                )
            reference = struct.unpack(">f", sec[11:15])[0]
            binary_scale = _sign_magnitude(int.from_bytes(sec[15:17], "big"), 16)
            decimal_scale = _sign_magnitude(int.from_bytes(sec[17:19], "big"), 16)
            packing = (reference, binary_scale, decimal_scale, sec[19], npoints)

        elif num == 6:
            indicator = sec[5]
            if indicator == 255:
                bitmap = None
            elif indicator == 0:
                bitmap = np.unpackbits(np.frombuffer(sec[6:], dtype=np.uint8)).astype(bool)
            else:
                raise Grib2Error(f"vordefinierte Bitmap {indicator} wird nicht unterstützt")

        elif num == 7:
            payload = sec[5:]

    if grid is None or packing is None or payload is None:
        raise Grib2Error("Nachricht ohne Gitter-, Packungs- oder Datensektion")
    if reference_time is None or forecast_time is None:
        raise Grib2Error("Nachricht ohne Zeitangaben")

    reference, binary_scale, decimal_scale, nbits, npoints = packing
    packed = _unpack(payload, nbits, npoints)
    scaled = (reference + packed * (2.0**binary_scale)) / (10.0**decimal_scale)

    if bitmap is None:
        if npoints != grid.size:
            raise Grib2Error(f"{npoints} Werte passen nicht zum Gitter mit {grid.size} Punkten")
        values = scaled.astype(np.float32)
    else:
        bitmap = bitmap[: grid.size]
        present = int(bitmap.sum())
        if present != npoints:
            raise Grib2Error(f"Bitmap markiert {present} Punkte, Daten enthalten {npoints}")
        values = np.full(grid.size, np.nan, dtype=np.float32)
        values[bitmap] = scaled

    return Grib2Message(
        grid=grid,
        discipline=discipline,
        parameter_category=category,
        parameter_number=number,
        first_surface=first_surface,
        second_surface=second_surface,
        reference_time=reference_time,
        forecast_time=forecast_time,
        values=values.reshape(grid.shape),
    )


def sample_bilinear(values: np.ndarray, grid: LatLonGrid, lat: float, lon: float) -> float | None:
    """Bilinear interpolierter Wert. ``None`` außerhalb des Gitters oder im Loch."""
    if not grid.contains(lat, lon):
        return None
    fj, fi = grid.fractional_index(lat, lon)
    j0, i0 = int(fj), int(fi)
    j1, i1 = min(j0 + 1, grid.nj - 1), min(i0 + 1, grid.ni - 1)
    wj, wi = fj - j0, fi - i0

    corners = np.array(
        [values[j0, i0], values[j0, i1], values[j1, i0], values[j1, i1]], dtype=np.float64
    )
    weights = np.array(
        [(1 - wj) * (1 - wi), (1 - wj) * wi, wj * (1 - wi), wj * wi], dtype=np.float64
    )

    valid = np.isfinite(corners)
    if not valid.any():
        return None
    if not valid.all():
        # Am Rand der ICON-D2-Domäne fehlen einzelne Ecken; dann nur über die
        # vorhandenen mitteln statt NaN durchzureichen.
        weights = np.where(valid, weights, 0.0)
        total = weights.sum()
        if total <= 0:
            return None
        weights /= total
        corners = np.where(valid, corners, 0.0)
    return float(corners @ weights)
