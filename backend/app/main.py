"""FastAPI-Anwendung.

Kein CORS: Frontend und API werden von Caddy unter demselben Origin
ausgeliefert. Wer die API von woanders aufruft, soll das bewusst
freischalten müssen.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import router
from .db import close_pool, open_pool

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await open_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="SoFi 2026",
    description="Backend zur partiellen Sonnenfinsternis am 12.08.2026 in Deutschland",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
)
app.include_router(router)
