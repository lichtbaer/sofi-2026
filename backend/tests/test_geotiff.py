"""Tests für den GeoTIFF-Leser.

Wie beim GRIB2-Leser wird die Datei synthetisch gebaut statt eine 30-MB-Kachel
ins Repository zu legen. Geprüft wird damit der Weg, der bei der echten Kachel
auch läuft: IFD lesen, Deflate entpacken, Fließkomma-Predictor rückgängig
machen, Kachelblöcke an die richtige Stelle setzen.

Der Predictor bekommt hier ein eigenes Gegenstück — ``_encode``. Ein Test, der
denselben Denkfehler wie der Leser macht, prüft nichts; der Encoder ist
deshalb aus der TIFF-Spezifikation geschrieben und nicht aus dem Leser
abgeleitet: Bytes in vier Ebenen zerlegen (höchstwertiges zuerst), dann
horizontal differenzieren.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest

from app.geotiff import GeoTiffError, read

_TILE = 16


def _encode(values: np.ndarray) -> bytes:
    """Fließkomma-Predictor anwenden — die Umkehrung von ``_undo_fp_predictor``."""
    rows, cols = values.shape
    little = values.astype("<f4").view(np.uint8).reshape(rows, cols, 4)
    planes = np.empty((rows, 4, cols), dtype=np.uint8)
    for plane in range(4):
        # Ebene 0 trägt das höchstwertige Byte; little-endian liegt es an Index 3.
        planes[:, plane, :] = little[..., 3 - plane]
    flat = planes.reshape(rows, cols * 4)
    diff = np.empty_like(flat)
    diff[:, 0] = flat[:, 0]
    diff[:, 1:] = (flat[:, 1:].astype(np.int16) - flat[:, :-1].astype(np.int16)).astype(np.uint8)
    return diff.tobytes()


def _build_tiff(
    values: np.ndarray,
    *,
    lat_top: float = 51.0,
    lon_left: float = 8.0,
    scale: float = 1 / 3600,
    compression: int = 8,
    predictor: int = 3,
    sample_format: int = 3,
    bits: int = 32,
) -> bytes:
    height, width = values.shape
    across = (width + _TILE - 1) // _TILE
    down = (height + _TILE - 1) // _TILE

    blocks: list[bytes] = []
    for row in range(down):
        for col in range(across):
            block = np.zeros((_TILE, _TILE), dtype=np.float32)
            chunk = values[row * _TILE : (row + 1) * _TILE, col * _TILE : (col + 1) * _TILE]
            block[: chunk.shape[0], : chunk.shape[1]] = chunk
            blocks.append(zlib.compress(_encode(block)))

    body = b"".join(blocks)
    data_start = 8
    offsets, position = [], data_start
    for block in blocks:
        offsets.append(position)
        position += len(block)

    # (Tag, Typ, Werte). Typ 3 = SHORT, 4 = LONG, 12 = DOUBLE.
    fields = [
        (256, 3, [width]), (257, 3, [height]), (258, 3, [bits]),
        (259, 3, [compression]), (262, 3, [1]), (277, 3, [1]),
        (317, 3, [predictor]), (322, 3, [_TILE]), (323, 3, [_TILE]),
        (324, 4, offsets), (325, 4, [len(b) for b in blocks]),
        (339, 3, [sample_format]),
        (33550, 12, [scale, scale, 0.0]),
        (33922, 12, [0.0, 0.0, 0.0, lon_left, lat_top, 0.0]),
    ]
    fields.sort()

    ifd_offset = data_start + len(body)
    # Zwei Byte Anzahl, zwölf je Eintrag, vier für den Zeiger auf die nächste
    # IFD — direkt dahinter beginnen die ausgelagerten Werte.
    extra_offset = ifd_offset + 2 + 12 * len(fields) + 4

    sizes, codes = {3: 2, 4: 4, 12: 8}, {3: "H", 4: "I", 12: "d"}
    ifd, extra = struct.pack("<H", len(fields)), b""
    for tag, typ, values in fields:
        packed = struct.pack(f"<{len(values)}{codes[typ]}", *values)
        # Werte bis vier Byte stehen laut Spezifikation *im* Eintrag, nicht
        # dahinter. Bei einem einzigen Kachelblock trifft das auch TileOffsets
        # und TileByteCounts — der Fall, den ein 2x3-Testbild auslöst.
        if sizes[typ] * len(values) <= 4:
            payload = packed.ljust(4, b"\x00")
        else:
            payload = struct.pack("<I", extra_offset + len(extra))
            extra += packed
        ifd += struct.pack("<HHI", tag, typ, len(values)) + payload
    ifd += struct.pack("<I", 0)

    assert extra_offset == ifd_offset + len(ifd), (extra_offset, ifd_offset + len(ifd))
    return struct.pack("<2sHI", b"II", 42, ifd_offset) + body + ifd + extra


def _write(tmp_path, values, **kwargs):
    path = tmp_path / "kachel.tif"
    path.write_bytes(_build_tiff(values, **kwargs))
    return path


def test_liest_werte_und_georeferenz(tmp_path):
    values = np.arange(40 * 40, dtype=np.float32).reshape(40, 40) / 7.0
    grid = read(_write(tmp_path, values))

    assert grid.shape == (40, 40)
    assert np.array_equal(grid.values, values)
    # AREA_OR_POINT = Point: der Tiepoint ist die Zellmitte, ohne Halbzellenversatz.
    assert grid.lat_first == pytest.approx(51.0)
    assert grid.lon_first == pytest.approx(8.0)
    assert grid.dlat == pytest.approx(-1 / 3600)
    assert grid.dlon == pytest.approx(1 / 3600)


def test_raender_werden_beschnitten(tmp_path):
    """Die letzte Kachelspalte ragt über das Bild hinaus und muss abgeschnitten werden."""
    values = np.random.default_rng(7).normal(300, 40, (35, 21)).astype(np.float32)
    grid = read(_write(tmp_path, values))
    assert grid.shape == (35, 21)
    assert np.array_equal(grid.values, values)


def test_negative_und_grosse_hoehen(tmp_path):
    values = np.array([[-11.5, 0.0, 2962.0], [8848.0, -420.0, 1.25]], dtype=np.float32)
    grid = read(_write(tmp_path, values))
    assert np.array_equal(grid.values, values)


@pytest.mark.parametrize(
    "kwargs, hinweis",
    [
        ({"compression": 5}, "Deflate"),
        ({"predictor": 2}, "Predictor"),
        ({"sample_format": 1}, "float32"),
        ({"bits": 16}, "float32"),
    ],
)
def test_weist_fremde_bauart_ab(tmp_path, kwargs, hinweis):
    """Lieber abbrechen als still falsch lesen — eine falsche Höhe sieht plausibel aus."""
    values = np.zeros((16, 16), dtype=np.float32)
    with pytest.raises(GeoTiffError, match=hinweis):
        read(_write(tmp_path, values, **kwargs))


def test_weist_fremdes_dateiformat_ab(tmp_path):
    path = tmp_path / "kaputt.tif"
    path.write_bytes(b"MM\x00\x2a" + b"\x00" * 64)
    with pytest.raises(GeoTiffError, match="classic TIFF"):
        read(path)
