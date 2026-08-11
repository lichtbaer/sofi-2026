"""Minimaler GeoTIFF-Leser für die Copernicus-DEM-Kacheln.

Dasselbe Motiv wie ``grib2.py``: die Kacheln kommen in genau einer Ausprägung,
und dafür lohnt GDAL im Image nicht. Gelesen wird ausschließlich, was
Copernicus GLO-30 tatsächlich liefert:

    classic TIFF · little endian · ein Band · float32 · gekachelt 1024×1024
    Compression 8 (Adobe Deflate) · Predictor 3 (Fließkomma)

Alles andere führt zu ``GeoTiffError``. Ein stillschweigend falsch gelesenes
Höhenraster wäre der schlimmste Ausgang — die Zahl sieht plausibel aus und ist
falsch, und niemand im Frontend erkennt es als Datenfehler.

Predictor 3 ist der Grund, warum das hier überhaupt Code braucht. Er speichert
eine Zeile nicht als Folge von Werten, sondern zerlegt jeden float32 in seine
vier Bytes und legt diese in vier Ebenen hintereinander — erst alle höchsten
Bytes, dann alle zweithöchsten und so fort. Über diese Bytefolge läuft dann
eine horizontale Differenzbildung. Rückwärts heißt das: erst kumulativ
aufsummieren (mod 256), dann die vier Ebenen wieder verschränken. Die erste
Ebene trägt das höchstwertige Byte, auf Little-Endian landet sie deshalb an
Position 3.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: TIFF-Tags, die gelesen werden.
_WIDTH, _LENGTH, _BITS, _COMPRESSION = 256, 257, 258, 259
_SAMPLES, _PREDICTOR = 277, 317
_TILE_WIDTH, _TILE_LENGTH, _TILE_OFFSETS, _TILE_BYTES = 322, 323, 324, 325
_SAMPLE_FORMAT = 339
_PIXEL_SCALE, _TIE_POINT = 33550, 33922

#: Bytes je TIFF-Feldtyp, soweit hier vorkommend.
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}
_TYPE_FMT = {1: "B", 2: "c", 3: "H", 4: "I", 11: "f", 12: "d"}


class GeoTiffError(Exception):
    """Die Datei ist keine Kachel der erwarteten Bauart."""


@dataclass(frozen=True, slots=True)
class Grid:
    """Ein gelesenes Höhenraster samt Georeferenz.

    ``lat_first``/``lon_first`` bezeichnen die Mitte der oberen linken Zelle,
    ``dlat`` ist negativ (die Zeilen laufen nach Süden).
    """

    values: np.ndarray
    lat_first: float
    lon_first: float
    dlat: float
    dlon: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape


def _read_tag_values(data: bytes, typ: int, count: int, payload: bytes) -> tuple:
    size = _TYPE_SIZE.get(typ)
    if size is None:
        raise GeoTiffError(f"unbekannter TIFF-Feldtyp {typ}")
    total = size * count
    raw = payload[:total] if total <= 4 else data[struct.unpack("<I", payload)[0] :][:total]
    return struct.unpack(f"<{count}{_TYPE_FMT[typ]}", raw)


def _read_ifd(data: bytes) -> dict[int, tuple]:
    if data[:2] != b"II" or struct.unpack("<H", data[2:4])[0] != 42:
        raise GeoTiffError("kein classic TIFF in Little-Endian")
    offset = struct.unpack("<I", data[4:8])[0]
    count = struct.unpack("<H", data[offset : offset + 2])[0]
    tags: dict[int, tuple] = {}
    for i in range(count):
        entry = data[offset + 2 + i * 12 : offset + 14 + i * 12]
        tag, typ, n = struct.unpack("<HHI", entry[:8])
        tags[tag] = _read_tag_values(data, typ, n, entry[8:12])
    return tags


def _undo_fp_predictor(raw: bytes, width: int, rows: int) -> np.ndarray:
    """Fließkomma-Predictor rückgängig machen. Siehe Modulkopf."""
    stream = np.frombuffer(raw, dtype=np.uint8, count=rows * width * 4).reshape(rows, width * 4)
    # Kumulativ mod 256 — der Überlauf von uint8 ist hier die gewollte Rechnung.
    accumulated = np.cumsum(stream, axis=1, dtype=np.uint8)
    planes = accumulated.reshape(rows, 4, width)
    out = np.empty((rows, width, 4), dtype=np.uint8)
    for plane in range(4):
        out[..., 3 - plane] = planes[:, plane, :]
    return out.reshape(rows, width * 4).view(np.float32)


def read(path: Path | str) -> Grid:
    """Liest eine Copernicus-Kachel vollständig ins Gedächtnis (~33 MB als float32)."""
    data = Path(path).read_bytes()
    tags = _read_ifd(data)

    def one(tag: int, name: str):
        if tag not in tags:
            raise GeoTiffError(f"Tag {name} fehlt")
        return tags[tag][0]

    if one(_COMPRESSION, "Compression") != 8:
        raise GeoTiffError("nur Adobe Deflate (8) wird gelesen")
    if one(_PREDICTOR, "Predictor") != 3:
        raise GeoTiffError("nur der Fließkomma-Predictor (3) wird gelesen")
    if one(_SAMPLE_FORMAT, "SampleFormat") != 3 or one(_BITS, "BitsPerSample") != 32:
        raise GeoTiffError("nur float32 wird gelesen")
    if one(_SAMPLES, "SamplesPerPixel") != 1:
        raise GeoTiffError("nur einbandige Kacheln werden gelesen")

    width, height = one(_WIDTH, "ImageWidth"), one(_LENGTH, "ImageLength")
    tile_w, tile_h = one(_TILE_WIDTH, "TileWidth"), one(_TILE_LENGTH, "TileLength")
    offsets, counts = tags[_TILE_OFFSETS], tags[_TILE_BYTES]

    across = (width + tile_w - 1) // tile_w
    down = (height + tile_h - 1) // tile_h
    if len(offsets) != across * down:
        raise GeoTiffError(f"{len(offsets)} Kachelblöcke, erwartet {across * down}")

    values = np.empty((height, width), dtype=np.float32)
    for index, (offset, length) in enumerate(zip(offsets, counts)):
        block = _undo_fp_predictor(
            zlib.decompress(data[offset : offset + length]), tile_w, tile_h
        )
        row, col = divmod(index, across)
        y0, x0 = row * tile_h, col * tile_w
        y1, x1 = min(y0 + tile_h, height), min(x0 + tile_w, width)
        values[y0:y1, x0:x1] = block[: y1 - y0, : x1 - x0]

    # ModelPixelScale (dx, dy, dz) und ModelTiepoint (i, j, k, x, y, z).
    # Die Kacheln tragen AREA_OR_POINT = Point: der Tiepoint bezeichnet bereits
    # die *Mitte* der Zelle (0, 0), nicht ihre Ecke. Keine Halbzellenkorrektur.
    scale, tie = tags[_PIXEL_SCALE], tags[_TIE_POINT]
    return Grid(
        values=values,
        lat_first=tie[4],
        lon_first=tie[3],
        dlat=-scale[1],
        dlon=scale[0],
    )
