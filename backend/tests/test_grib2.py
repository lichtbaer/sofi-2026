"""Tests für den GRIB2-Leser.

Die Nachrichten werden hier synthetisch gebaut statt eine 500-kB-Datei ins
Repository zu legen: so ist geprüft, dass Bitentpackung, Bitmap, Skalierung und
Scan-Richtung stimmen, und der Test läuft ohne Netz.
"""

from __future__ import annotations

import math
import struct
from datetime import UTC, datetime

import numpy as np
import pytest

from app.grib2 import (
    MISSING_SURFACE,
    FixedSurface,
    Grib2Error,
    LatLonGrid,
    decode,
    sample_bilinear,
)


def _sign_magnitude(value: int, nbytes: int) -> bytes:
    raw = abs(value) | (1 << (nbytes * 8 - 1)) if value < 0 else value
    return raw.to_bytes(nbytes, "big")


def _pack(values: list[int], nbits: int) -> bytes:
    out = bytearray()
    acc = held = 0
    for value in values:
        acc = (acc << nbits) | value
        held += nbits
        while held >= 8:
            held -= 8
            out.append((acc >> held) & 0xFF)
    if held:
        out.append((acc << (8 - held)) & 0xFF)
    return bytes(out)


def _section(number: int, body: bytes) -> bytes:
    return struct.pack(">IB", len(body) + 5, number) + body


def build_message(
    *,
    ni: int = 5,
    nj: int = 4,
    lat1: float = 47.0,
    lon1: float = 5.0,
    step: float = 0.5,
    scanning: int = 0x40,
    values: list[int],
    nbits: int = 8,
    binary_scale: int = 0,
    decimal_scale: int = 0,
    reference: float = 0.0,
    bitmap: list[bool] | None = None,
    reference_time: datetime = datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
    forecast_minutes: int = 42 * 60,
    data_template: int = 0,
    parameter: tuple[int, int] = (6, 1),
    surfaces: tuple[tuple[int, int, int], tuple[int, int, int]] = (
        (1, 0, 0),
        (255, 255, 0xFFFFFFFF),
    ),
) -> bytes:
    lat2 = lat1 + (step if scanning & 0x40 else -step) * (nj - 1)
    lon2 = lon1 + (-step if scanning & 0x80 else step) * (ni - 1)
    micro = lambda v: _sign_magnitude(round(v * 1e6), 4)  # noqa: E731

    s1 = _section(
        1,
        struct.pack(
            ">HHBBBHBBBBBBB",
            78, 255, 2, 1, 1,
            reference_time.year, reference_time.month, reference_time.day,
            reference_time.hour, reference_time.minute, reference_time.second,
            0, 1,
        ),
    )

    s3 = _section(
        3,
        struct.pack(">BIBBH", 0, ni * nj, 0, 0, 0)          # Quelle, Punkte, Liste, Template
        + bytes([6, 0]) + b"\x00" * 4                        # Erdfigur
        + bytes([0]) + b"\x00" * 4 + bytes([0]) + b"\x00" * 4
        + struct.pack(">II", ni, nj)
        + b"\x00" * 8                                        # Basiswinkel + Unterteilung
        + micro(lat1) + micro(lon1 % 360)
        + bytes([0x30])                                      # Auflösungsflags
        + micro(lat2) + micro(lon2 % 360)
        + struct.pack(">II", round(step * 1e6), round(step * 1e6))
        + bytes([scanning]),
    )

    s4 = _section(
        4,
        struct.pack(">HH", 0, 0)                             # Koordinatenwerte, Template 4.0
        + bytes(parameter)                                   # Kategorie, Parameternummer
        + bytes([2, 0, 11])
        + struct.pack(">HB", 0, 0)
        + bytes([0])                                         # Zeiteinheit: Minuten
        + struct.pack(">I", forecast_minutes)
        + b"".join(struct.pack(">BBI", *surface) for surface in surfaces),
    )

    packed = _pack(values, nbits)
    s5 = _section(
        5,
        struct.pack(">IH", len(values), data_template)
        + struct.pack(">f", reference)
        + _sign_magnitude(binary_scale, 2)
        + _sign_magnitude(decimal_scale, 2)
        + bytes([nbits, 0]),
    )

    if bitmap is None:
        s6 = _section(6, bytes([255]))
    else:
        bits = np.packbits(np.array(bitmap, dtype=np.uint8)).tobytes()
        s6 = _section(6, bytes([0]) + bits)

    s7 = _section(7, packed)

    body = s1 + s3 + s4 + s5 + s6 + s7 + b"7777"
    header = b"GRIB" + b"\x00\x00" + bytes([0, 2])
    total = len(header) + 8 + len(body)
    return header + total.to_bytes(8, "big") + body


def test_decodes_grid_and_values() -> None:
    values = list(range(20))
    message = decode(build_message(values=values))

    assert message.grid == LatLonGrid(ni=5, nj=4, lat_first=47.0, lon_first=5.0, dlat=0.5, dlon=0.5)
    assert message.grid.bounds() == pytest.approx((47.0, 5.0, 48.5, 7.0))
    assert message.values.shape == (4, 5)
    np.testing.assert_array_equal(message.values, np.arange(20, dtype=np.float32).reshape(4, 5))

    assert message.reference_time == datetime(2026, 8, 11, tzinfo=UTC)
    assert message.valid_time == datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
    assert message.signature == (0, 6, 1, FixedSurface(1, 0.0), MISSING_SURFACE)


def test_pressure_layers_are_read_from_the_product_section() -> None:
    """So trennt der DWD tiefe, mittlere und hohe Bewölkung — über Druckflächen."""
    message = decode(
        build_message(
            values=[1] * 20,
            parameter=(6, 22),
            surfaces=((100, 0, 80000), (1, 0, 0)),
        )
    )
    assert message.signature == (0, 6, 22, FixedSurface(100, 80000.0), FixedSurface(1, 0.0))


def test_surface_scale_factor_is_applied() -> None:
    message = decode(
        build_message(values=[1] * 20, surfaces=((103, 1, 20), (255, 255, 0xFFFFFFFF)))
    )
    assert message.first_surface == FixedSurface(103, 2.0)
    assert message.second_surface == MISSING_SURFACE


def test_binary_and_decimal_scaling() -> None:
    """value = (R + X · 2^E) / 10^D, mit Vorzeichen-Betrag-Kodierung von E und D."""
    message = decode(
        build_message(values=[512] * 20, nbits=16, binary_scale=-9, decimal_scale=0, reference=1.5)
    )
    assert message.values[0, 0] == pytest.approx(2.5)

    message = decode(build_message(values=[250] * 20, binary_scale=0, decimal_scale=1))
    assert message.values[0, 0] == pytest.approx(25.0)


def test_non_byte_aligned_packing() -> None:
    values = [i * 137 % 4096 for i in range(20)]
    message = decode(build_message(values=values, nbits=12))
    np.testing.assert_array_equal(
        message.values, np.array(values, dtype=np.float32).reshape(4, 5)
    )


def test_bitmap_marks_missing_points_as_nan() -> None:
    bitmap = [True] * 20
    bitmap[3] = bitmap[11] = False
    message = decode(build_message(values=[7] * 18, bitmap=bitmap))

    flat = message.values.ravel()
    assert math.isnan(flat[3]) and math.isnan(flat[11])
    assert np.nansum(flat) == pytest.approx(7 * 18)


def test_north_to_south_scan_is_reflected_in_step_sign() -> None:
    message = decode(build_message(values=list(range(20)), scanning=0x00))
    assert message.grid.dlat == pytest.approx(-0.5)
    assert message.grid.bounds() == pytest.approx((45.5, 5.0, 47.0, 7.0))


def test_longitudes_above_180_become_negative() -> None:
    message = decode(build_message(values=list(range(20)), lon1=356.06))
    assert message.grid.lon_first == pytest.approx(-3.94)


def test_rejects_unsupported_packing() -> None:
    with pytest.raises(Grib2Error, match="simple packing"):
        decode(build_message(values=list(range(20)), data_template=42))


def test_rejects_truncated_message() -> None:
    buf = build_message(values=list(range(20)))
    with pytest.raises(Grib2Error):
        decode(buf[:-40])


def test_rejects_bitmap_that_disagrees_with_data() -> None:
    bitmap = [True] * 20
    bitmap[0] = False
    with pytest.raises(Grib2Error, match="Bitmap"):
        decode(build_message(values=[1] * 20, bitmap=bitmap))


def test_sample_bilinear_interpolates_and_respects_bounds() -> None:
    message = decode(build_message(values=list(range(20))))
    grid = message.grid

    assert sample_bilinear(message.values, grid, 47.0, 5.0) == pytest.approx(0.0)
    assert sample_bilinear(message.values, grid, 47.25, 5.25) == pytest.approx(3.0)
    assert sample_bilinear(message.values, grid, 48.5, 7.0) == pytest.approx(19.0)
    assert sample_bilinear(message.values, grid, 60.0, 5.0) is None


def test_sample_bilinear_falls_back_to_valid_corners() -> None:
    bitmap = [True] * 20
    bitmap[0] = False
    message = decode(build_message(values=list(range(1, 20)), bitmap=bitmap))

    # Genau auf dem fehlenden Punkt gibt es nichts zu mitteln.
    assert sample_bilinear(message.values, message.grid, 47.0, 5.0) is None
    # Zwischen den Punkten trägt die Lücke einfach nicht bei: Mittel aus 1, 5, 6.
    assert sample_bilinear(message.values, message.grid, 47.25, 5.25) == pytest.approx(4.0)
