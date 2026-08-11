"""Ingest der ICON-D2-Wolkenfelder von opendata.dwd.de.

ICON-D2 ist das hochauflösende Modell des DWD (0,02° ≈ 2,2 km, 48 h Vorlauf,
alle 3 h ein neuer Lauf). Wir holen nicht den kompletten Lauf, sondern nur die
Vorhersagezeitpunkte rund um die Finsternis — vier Wolkenvariablen zu fünf
Zeitpunkten, rund 10 MB pro Lauf.

Warum vier statt nur Gesamtbedeckung: bei 2–7° Sonnenhöhe ist der Unterschied
zwischen hohen Zirren und tiefem Stratus entscheidend. Durch Zirren sieht man
die Sichel, durch Hochnebel nicht. ``clct`` allein würde beides gleich bewerten.
"""

from __future__ import annotations

import asyncio
import bz2
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np

from ..config import Settings, get_settings
from ..db import connection
from ..grib2 import MISSING_SURFACE, FixedSurface, Grib2Message, LatLonGrid, decode

log = logging.getLogger(__name__)

MODEL = "icon-d2"
NODATA = 255

_FILENAME = re.compile(
    r"icon-d2_germany_regular-lat-lon_single-level_(\d{10})_(\d{3})_2d_([a-z_0-9]+)\.grib2\.bz2"
)

#: Gegenprobe, dass eine Datei enthält, was ihr Name verspricht.
#:
#: Die Parameternummer allein reicht nicht: der DWD kodiert tiefe, mittlere und
#: hohe Bewölkung alle als 0/6/22 („cloud cover") und trennt sie ausschließlich
#: über die begrenzenden Druckflächen (Typ 100, Wert in Pa). Verwechselte man
#: hier zwei Dateien, käme ein plausibel aussehender, aber falscher
#: Verdeckungsgrad heraus — hoher Zirrus wiegt in der Bewertung viel leichter
#: als Hochnebel.
_EXPECTED_SIGNATURE: dict[str, tuple[int, int, int, FixedSurface, FixedSurface]] = {
    # Gesamtbedeckung, bezogen auf den Boden.
    "clct": (0, 6, 1, FixedSurface(1, 0.0), MISSING_SURFACE),
    # Tief: Boden bis 800 hPa.
    "clcl": (0, 6, 22, FixedSurface(100, 80000.0), FixedSurface(1, 0.0)),
    # Mittel: 800 bis 400 hPa.
    "clcm": (0, 6, 22, FixedSurface(100, 40000.0), FixedSurface(100, 80000.0)),
    # Hoch: 400 hPa bis Modelloberkante.
    "clch": (0, 6, 22, FixedSurface(100, 0.0), FixedSurface(100, 40000.0)),
}


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunAvailability:
    run_at: datetime
    steps: frozenset[int]

    def covers(self, valid_times: list[datetime]) -> bool:
        return all(int((v - self.run_at).total_seconds() // 3600) in self.steps for v in valid_times)


def target_valid_times(settings: Settings) -> list[datetime]:
    return [
        datetime(
            settings.event_date.year,
            settings.event_date.month,
            settings.event_date.day,
            hour,
            tzinfo=UTC,
        )
        for hour in settings.event_hours_utc
    ]


def file_url(settings: Settings, run_at: datetime, variable: str, step: int) -> str:
    stamp = run_at.strftime("%Y%m%d%H")
    return (
        f"{settings.icon_base_url}/{run_at:%H}/{variable}/"
        f"icon-d2_germany_regular-lat-lon_single-level_{stamp}_{step:03d}_2d_{variable}.grib2.bz2"
    )


async def probe_run_hour(client: httpx.AsyncClient, settings: Settings, hour: int) -> RunAvailability | None:
    """Liest das Verzeichnis einer Laufstunde und meldet Lauf und fertige Schritte.

    Auf dem Server liegt je Laufstunde immer nur der jüngste Lauf; welcher das
    ist, verrät erst der Zeitstempel in den Dateinamen.
    """
    url = f"{settings.icon_base_url}/{hour:02d}/clct/"
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Verzeichnis %s nicht lesbar: %s", url, exc)
        return None

    stamps: set[str] = set()
    steps: set[int] = set()
    for match in _FILENAME.finditer(response.text):
        stamps.add(match.group(1))
        steps.add(int(match.group(2)))

    if len(stamps) != 1:
        log.warning("Verzeichnis %s enthält %d Laufzeitpunkte, übersprungen", url, len(stamps))
        return None

    run_at = datetime.strptime(stamps.pop(), "%Y%m%d%H").replace(tzinfo=UTC)
    return RunAvailability(run_at=run_at, steps=frozenset(steps))


async def newest_usable_run(
    client: httpx.AsyncClient, settings: Settings
) -> RunAvailability | None:
    """Jüngster Lauf, der alle gebrauchten Zeitpunkte bereits veröffentlicht hat."""
    valid_times = target_valid_times(settings)
    horizon = timedelta(hours=settings.icon_max_lead_hours)
    now = datetime.now(UTC)

    probes = await asyncio.gather(
        *(probe_run_hour(client, settings, h) for h in settings.icon_run_hours)
    )
    candidates = [
        p
        for p in probes
        if p is not None
        and p.run_at <= now
        and all(timedelta(0) <= v - p.run_at <= horizon for v in valid_times)
        and p.covers(valid_times)
    ]
    return max(candidates, key=lambda p: p.run_at, default=None)


async def _download_field(
    client: httpx.AsyncClient,
    settings: Settings,
    run_at: datetime,
    variable: str,
    valid_at: datetime,
) -> Grib2Message:
    step = int((valid_at - run_at).total_seconds() // 3600)
    url = file_url(settings, run_at, variable, step)

    response = await client.get(url)
    response.raise_for_status()
    message = await asyncio.to_thread(lambda: decode(bz2.decompress(response.content)))

    expected = _EXPECTED_SIGNATURE[variable]
    if message.signature != expected:
        raise IngestError(
            f"{url}: Kennung {message.signature}, erwartet {expected} für {variable}"
        )
    if message.valid_time != valid_at:
        raise IngestError(f"{url}: gültig {message.valid_time}, erwartet {valid_at}")
    return message


def _quantise(values: np.ndarray) -> np.ndarray:
    """Bewölkung in Prozent als uint8, fehlende Punkte als 255.

    1 % Auflösung — deutlich feiner als die Aussagekraft einer 42-Stunden-
    Prognose, und das Array ist danach direkt als PNG-Kanal verwendbar.
    """
    filled = np.nan_to_num(values, nan=float(NODATA))
    clipped = np.clip(np.rint(filled), 0, 100).astype(np.uint8)
    return np.where(np.isfinite(values), clipped, np.uint8(NODATA)).astype(np.uint8)


def field_path(settings: Settings, run_at: datetime, variable: str, valid_at: datetime) -> Path:
    return settings.icon_dir / run_at.strftime("%Y%m%dT%H") / f"{variable}_{valid_at:%Y%m%dT%H%M}.npy"


async def ingest_run(run: RunAvailability, settings: Settings | None = None) -> bool:
    """Holt einen Lauf vollständig. ``False``, wenn er schon vorlag."""
    settings = settings or get_settings()
    valid_times = target_valid_times(settings)

    async with connection() as conn:
        row = await (
            await conn.execute(
                "SELECT id, finished_at FROM forecast_run WHERE model = %s AND run_at = %s",
                (MODEL, run.run_at),
            )
        ).fetchone()
        if row and row["finished_at"] is not None:
            return False

        run_id = (
            row["id"]
            if row
            else (
                await (
                    await conn.execute(
                        "INSERT INTO forecast_run (model, run_at) VALUES (%s, %s) RETURNING id",
                        (MODEL, run.run_at),
                    )
                ).fetchone()
            )["id"]
        )

    run_dir = settings.icon_dir / run.run_at.strftime("%Y%m%dT%H")
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("Lauf %s wird geholt (%d Felder)", run.run_at, len(valid_times) * len(settings.icon_variables))

    grid: LatLonGrid | None = None
    limit = asyncio.Semaphore(4)

    async with httpx.AsyncClient(timeout=settings.http_timeout_s, follow_redirects=True) as client:

        async def fetch_one(variable: str, valid_at: datetime) -> tuple[str, datetime, LatLonGrid]:
            async with limit:
                message = await _download_field(client, settings, run.run_at, variable, valid_at)
            path = field_path(settings, run.run_at, variable, valid_at)
            await asyncio.to_thread(np.save, path, _quantise(message.values))
            return variable, valid_at, message.grid

        try:
            results = await asyncio.gather(
                *(
                    fetch_one(variable, valid_at)
                    for variable in settings.icon_variables
                    for valid_at in valid_times
                )
            )
        except Exception:
            # Unvollständige Läufe bleiben ohne finished_at und damit unsichtbar;
            # die Reste räumen wir trotzdem gleich weg.
            shutil.rmtree(run_dir, ignore_errors=True)
            async with connection() as conn:
                await conn.execute("DELETE FROM forecast_run WHERE id = %s", (run_id,))
            raise

    async with connection() as conn:
        for variable, valid_at, field_grid in results:
            if grid is None:
                grid = field_grid
            elif field_grid != grid:
                raise IngestError("Felder eines Laufs mit unterschiedlichen Gittern")

            await conn.execute(
                """
                INSERT INTO forecast_field
                    (run_id, variable, valid_at, path, ni, nj, lat_first, lon_first, dlat, dlon, nodata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, variable, valid_at) DO UPDATE SET path = EXCLUDED.path
                """,
                (
                    run_id,
                    variable,
                    valid_at,
                    str(field_path(settings, run.run_at, variable, valid_at)),
                    field_grid.ni,
                    field_grid.nj,
                    field_grid.lat_first,
                    field_grid.lon_first,
                    field_grid.dlat,
                    field_grid.dlon,
                    NODATA,
                ),
            )
        await conn.execute(
            "UPDATE forecast_run SET finished_at = now() WHERE id = %s", (run_id,)
        )

    log.info("Lauf %s vollständig", run.run_at)
    return True


async def prune_old_runs(settings: Settings | None = None) -> int:
    """Behält die jüngsten ``keep_runs`` abgeschlossenen Läufe."""
    settings = settings or get_settings()
    async with connection() as conn:
        rows = await (
            await conn.execute(
                """
                DELETE FROM forecast_run
                WHERE model = %s AND id NOT IN (
                    SELECT id FROM forecast_run
                    WHERE model = %s AND finished_at IS NOT NULL
                    ORDER BY run_at DESC LIMIT %s
                )
                RETURNING run_at
                """,
                (MODEL, MODEL, settings.keep_runs),
            )
        ).fetchall()

    for row in rows:
        shutil.rmtree(settings.icon_dir / row["run_at"].strftime("%Y%m%dT%H"), ignore_errors=True)
    return len(rows)


async def sync(settings: Settings | None = None) -> bool:
    """Ein Durchlauf: neuesten brauchbaren Lauf holen, alte wegräumen."""
    settings = settings or get_settings()
    async with httpx.AsyncClient(timeout=settings.http_timeout_s, follow_redirects=True) as client:
        run = await newest_usable_run(client, settings)

    if run is None:
        log.warning("Kein ICON-D2-Lauf deckt das Ereignisfenster ab")
        return False

    fetched = await ingest_run(run, settings)
    if fetched:
        await prune_old_runs(settings)
    return fetched
