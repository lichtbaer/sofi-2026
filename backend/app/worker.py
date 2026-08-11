"""Hintergrundprozess: holt regelmäßig den jüngsten ICON-D2-Lauf.

Läuft als eigener Container. Ein Ingest, der die API blockiert oder mit ihr
zusammen neu startet, wäre am Ereignistag genau das falsche Verhalten.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from .config import get_settings
from .db import close_pool
from .services import icon_d2

log = logging.getLogger("worker")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s"
    )
    settings = get_settings()
    settings.icon_dir.mkdir(parents=True, exist_ok=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

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

    log.info("Worker beendet")
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
