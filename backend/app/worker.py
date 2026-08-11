"""Hintergrundprozess: holt das Höhenraster und regelmäßig den jüngsten
ICON-D2-Lauf.

Läuft als eigener Container. Ein Ingest, der die API blockiert oder mit ihr
zusammen neu startet, wäre am Ereignistag genau das falsche Verhalten.

Das Höhenraster wird einmal beim Start geprüft und, wenn es fehlt, geholt —
rund 3 GB Kacheln, die zu einem 2,85-GB-Mosaik verrechnet werden. Das dauert
Minuten und läuft deshalb *neben* der Wolkenschleife, nicht vor ihr: eine
fehlende Wolkenprognose am Ereignisabend wäre der teurere Ausfall. Der Aufbau
ist wiederaufnehmbar, ein Neustart mittendrin kostet nur die angefangene
Kachel.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from .config import Settings, get_settings
from .db import close_pool
from .services import icon_d2
from .services.dem import DemStore

log = logging.getLogger("worker")


async def ensure_terrain(settings: Settings, stop: asyncio.Event) -> None:
    """Höhenraster bereitstellen. Wiederholt, bis es vollständig ist."""
    store = DemStore(settings)
    while not stop.is_set():
        if store.ready:
            log.info("Höhenraster liegt vor")
            return
        try:
            log.info("Höhenraster unvollständig — Aufbau beginnt")
            await asyncio.to_thread(store.build)
        except Exception:
            log.exception("Aufbau des Höhenrasters fehlgeschlagen")
        if store.ready:
            log.info("Höhenraster vollständig")
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_interval_s)
        except TimeoutError:
            pass


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s"
    )
    settings = get_settings()
    settings.icon_dir.mkdir(parents=True, exist_ok=True)
    settings.dem_dir.mkdir(parents=True, exist_ok=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    terrain = asyncio.create_task(ensure_terrain(settings, stop))

    log.info("Worker gestartet, Intervall %d s", settings.worker_interval_s)
    while not stop.is_set():
        try:
            if await icon_d2.sync(settings):
                log.info("Neuer Lauf eingespielt")
            else:
                log.info("Kein neuer Lauf")
        except Exception:
            log.exception("Ingest fehlgeschlagen, nächster Versuch in %d s", settings.worker_interval_s)

        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_interval_s)
        except TimeoutError:
            pass

    terrain.cancel()
    try:
        await terrain
    except asyncio.CancelledError:
        pass

    log.info("Worker beendet")
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
