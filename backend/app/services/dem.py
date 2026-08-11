"""Höhenraster Copernicus DEM GLO-30, geholt und als memmap abgelegt.

Quelle: ``https://copernicus-dem-30m.s3.amazonaws.com`` (ESA/Copernicus, freie
Nutzung, keine Anmeldung). Eine Quelle, ein Format, eine Lizenz — der Grund,
warum hier GLO-30 steht und nicht DOM1 der Länder.

**GLO-30 ist ein Oberflächenmodell.** Es enthält Bewuchs: gemessen an der
Kachel N50/E008 liegt der Frankfurter Stadtwald 17 m über dem Vorfeld des
Flughafens, bei gleicher Geländehöhe der Rhein-Main-Ebene. Gebäude dagegen
fehlen weitgehend — der Commerzbank-Tower (259 m) liest sich als Bodenniveau.
Für einen Westhorizont im Freien ist das die richtige Asymmetrie: dort
limitieren Baumreihen, nicht Hochhäuser. Der verbleibende Fehler zeigt weiter
in eine Richtung, siehe ``horizon.py``.

Zwei Eigenheiten der Quelle, die man kennen muss:

* **Die Längenabtastung wechselt bei 50° N.** Südlich davon 1″ (3600 Spalten je
  Grad), nördlich 1,5″ (2400 Spalten). Die Grenze läuft mitten durch
  Deutschland — Frankfurt liegt auf 50,1°. Ein Mosaik, das das übersieht,
  verschiebt die halbe Republik um bis zu 15 km nach Osten, ohne dass die
  Zahlen unplausibel aussähen. Hier wird deshalb auf ein einheitliches
  1″-Gitter gelegt und das grobe Band spaltenweise wiederholt — nearest
  neighbour, keine erfundene Zwischenstufe.
* **Reine Seekacheln existieren nicht.** S3 antwortet mit ``NoSuchKey``. Das
  ist kein Fehler, sondern die Auskunft „hier ist nur Wasser"; solche Kacheln
  werden als erledigt vermerkt und nie wieder angefragt.

Abgelegt wird int16 in Dezimetern: 0,1 m Auflösung, Wertebereich bis 3276,7 m
(Zugspitze 2962 m). Ganze Meter wären zu grob — eine halbe Meter Unsicherheit
sind auf 90 m Entfernung schon 0,3°, und um solche Beträge geht es hier.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from ..config import Settings
from ..geotiff import GeoTiffError, read as read_geotiff

log = logging.getLogger("dem")

#: Zielgitter: 1 Bogensekunde in beiden Richtungen.
STEPS_PER_DEGREE = 3600
#: Fehlende Zelle. Der Raycaster überspringt sie, statt sie als Höhe 0 zu lesen.
NODATA = np.int16(-32768)
#: Größter Wert in Dezimetern, der noch in int16 passt.
_MAX_DM = 32767


def tile_name(lat: int, lon: int) -> str:
    return f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"


@dataclass(frozen=True, slots=True)
class Extent:
    """Gitterbereich des Mosaiks, in ganzen Gradkacheln."""

    lat_min: int
    lat_max: int
    lon_min: int
    lon_max: int

    @property
    def rows(self) -> int:
        return (self.lat_max + 1 - self.lat_min) * STEPS_PER_DEGREE

    @property
    def cols(self) -> int:
        return (self.lon_max + 1 - self.lon_min) * STEPS_PER_DEGREE

    @property
    def lat_top(self) -> float:
        return float(self.lat_max + 1)

    @property
    def lon_left(self) -> float:
        return float(self.lon_min)

    def tiles(self) -> list[tuple[int, int]]:
        return [
            (lat, lon)
            for lat in range(self.lat_min, self.lat_max + 1)
            for lon in range(self.lon_min, self.lon_max + 1)
        ]


def extent_for(settings: Settings) -> Extent:
    """Kachelbereich aus der Deutschland-Box plus Rand für das Fernfeld."""
    lat_min, lon_min, lat_max, lon_max = settings.germany_bbox
    margin_deg = settings.dem_margin_m / 111_320.0
    return Extent(
        lat_min=math.floor(lat_min - margin_deg),
        lat_max=math.floor(lat_max + margin_deg),
        lon_min=math.floor(lon_min - margin_deg / math.cos(math.radians(lat_max))),
        lon_max=math.floor(lon_max + margin_deg / math.cos(math.radians(lat_max))),
    )


def _column_map(source_cols: int) -> np.ndarray | None:
    """Spaltenzuordnung vom Quellgitter auf das 1″-Zielgitter.

    ``None``, wenn die Quelle bereits 1″ hat. Sonst der Index der jeweils
    nächstgelegenen Quellspalte für jede der 3600 Zielspalten.
    """
    if source_cols == STEPS_PER_DEGREE:
        return None
    ratio = source_cols / STEPS_PER_DEGREE
    idx = np.round(np.arange(STEPS_PER_DEGREE) * ratio).astype(np.int32)
    return np.clip(idx, 0, source_cols - 1)


class DemStore:
    """Das Mosaik auf der Platte, plus der Zustand seines Aufbaus."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.extent = extent_for(settings)
        self.dir = settings.dem_dir
        self.array_path = self.dir / "glo30_de.i16"
        self.state_path = self.dir / "glo30_de.json"
        self._values: np.memmap | None = None

    # ── Zustand ────────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except json.JSONDecodeError:
                log.warning("Zustandsdatei unlesbar, Aufbau beginnt von vorn")
        return {"done": [], "complete": False, "extent": self._extent_dict()}

    def _extent_dict(self) -> dict:
        e = self.extent
        return {"lat_min": e.lat_min, "lat_max": e.lat_max,
                "lon_min": e.lon_min, "lon_max": e.lon_max}

    def _save_state(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(self.state_path)

    @property
    def ready(self) -> bool:
        state = self._load_state()
        return bool(state.get("complete")) and state.get("extent") == self._extent_dict()

    # ── Aufbau ─────────────────────────────────────────────────────────────

    def build(self) -> None:
        """Holt fehlende Kacheln und faltet sie ins Mosaik. Wiederaufnehmbar.

        Jede Kachel wird geholt, entpackt, eingetragen und sofort wieder
        gelöscht: das hält den Spitzenbedarf bei der Mosaikgröße plus einer
        Kachel statt bei der Summe aus beidem.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        if state.get("extent") != self._extent_dict():
            log.info("Kachelbereich geändert — Mosaik wird neu aufgebaut")
            self.array_path.unlink(missing_ok=True)
            state = {"done": [], "complete": False, "extent": self._extent_dict()}

        expected = self.extent.rows * self.extent.cols * 2
        if not self.array_path.exists() or self.array_path.stat().st_size != expected:
            log.info(
                "Lege Mosaik an: %d x %d Zellen, %.2f GB",
                self.extent.rows, self.extent.cols, expected / 1e9,
            )
            self._allocate(expected)
            state["done"] = []

        done = set(state["done"])
        todo = [t for t in self.extent.tiles() if tile_name(*t) not in done]
        if not todo:
            state["complete"] = True
            self._save_state(state)
            return

        log.info("%d von %d Kacheln fehlen", len(todo), len(self.extent.tiles()))
        values = np.memmap(self.array_path, dtype=np.int16, mode="r+",
                           shape=(self.extent.rows, self.extent.cols))
        try:
            with httpx.Client(timeout=self.settings.http_timeout_s, follow_redirects=True) as client:
                for number, (lat, lon) in enumerate(todo, 1):
                    name = tile_name(lat, lon)
                    try:
                        self._ingest_tile(client, values, lat, lon)
                    except Exception:
                        log.exception("Kachel %s fehlgeschlagen — wird beim nächsten Lauf erneut versucht", name)
                        continue
                    done.add(name)
                    state["done"] = sorted(done)
                    self._save_state(state)
                    if number % 10 == 0 or number == len(todo):
                        log.info("%d/%d Kacheln eingetragen", number, len(todo))
            values.flush()
        finally:
            del values

        state["complete"] = len(done) >= len(self.extent.tiles())
        self._save_state(state)
        if state["complete"]:
            log.info("Höhenraster vollständig")

    def _allocate(self, size_bytes: int) -> None:
        """Legt die Mosaikdatei an und füllt sie mit NODATA."""
        chunk_rows = 256
        blank = np.full((chunk_rows, self.extent.cols), NODATA, dtype=np.int16).tobytes()
        with self.array_path.open("wb") as handle:
            written = 0
            while written + len(blank) <= size_bytes:
                handle.write(blank)
                written += len(blank)
            if written < size_bytes:
                handle.write(blank[: size_bytes - written])
        if self.array_path.stat().st_size != size_bytes:  # pragma: no cover
            raise RuntimeError("Mosaikdatei hat unerwartete Größe")

    def _ingest_tile(self, client: httpx.Client, values: np.memmap, lat: int, lon: int) -> None:
        name = tile_name(lat, lon)
        path = self.dir / f"{name}.tif"

        if not path.exists() or path.stat().st_size < 100_000:
            url = f"{self.settings.dem_base_url}/{name}/{name}.tif"
            response = client.get(url)
            if response.status_code == 404:
                log.info("%s existiert nicht (reine Seefläche)", name)
                return
            response.raise_for_status()
            # S3 meldet fehlende Objekte auch als 200 mit XML-Körper.
            if response.content[:2] != b"II":
                log.info("%s liefert kein TIFF (reine Seefläche)", name)
                return
            path.write_bytes(response.content)

        try:
            grid = read_geotiff(path)
        except GeoTiffError:
            log.exception("%s ist keine erwartete Kachel", name)
            path.unlink(missing_ok=True)
            return

        block = np.round(np.nan_to_num(grid.values, nan=float(NODATA)) * 10.0)
        block = np.clip(block, -_MAX_DM, _MAX_DM).astype(np.int16)
        column_map = _column_map(grid.shape[1])
        if column_map is not None:
            block = block[:, column_map]

        row0 = int(round((self.extent.lat_top - (lat + 1)) * STEPS_PER_DEGREE))
        col0 = int(round((lon - self.extent.lon_left) * STEPS_PER_DEGREE))
        rows, cols = block.shape
        values[row0 : row0 + rows, col0 : col0 + cols] = block
        path.unlink(missing_ok=True)

    # ── Abfrage ────────────────────────────────────────────────────────────

    def open(self) -> np.memmap:
        if self._values is None:
            self._values = np.memmap(
                self.array_path, dtype=np.int16, mode="r",
                shape=(self.extent.rows, self.extent.cols),
            )
        return self._values

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Höhen in Metern an den gegebenen Punkten, ``nan`` außerhalb.

        Nächster Nachbar. Bilinear wäre glatter, aber ein Oberflächenmodell
        soll gerade nicht geglättet werden: die Waldkante ist die Information.
        """
        values = self.open()
        row = np.rint((self.extent.lat_top - lat) * STEPS_PER_DEGREE).astype(np.int64)
        col = np.rint((lon - self.extent.lon_left) * STEPS_PER_DEGREE).astype(np.int64)
        inside = (row >= 0) & (row < self.extent.rows) & (col >= 0) & (col < self.extent.cols)
        raw = values[np.clip(row, 0, self.extent.rows - 1),
                     np.clip(col, 0, self.extent.cols - 1)]
        out = np.where(inside & (raw != NODATA), raw.astype(np.float64) / 10.0, np.nan)
        return out


_store: DemStore | None = None


def get_store(settings: Settings) -> DemStore:
    global _store
    if _store is None or _store.settings is not settings:
        _store = DemStore(settings)
    return _store
