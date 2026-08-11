"""Verbindungspool. Ein Pool pro Prozess, von API und Worker gleichermaßen genutzt."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings

_pool: AsyncConnectionPool | None = None


def _make_pool() -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo=get_settings().database_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row},
    )


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = _make_pool()
        await _pool.open(wait=True, timeout=30.0)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    pool = await open_pool()
    async with pool.connection() as conn:
        yield conn
