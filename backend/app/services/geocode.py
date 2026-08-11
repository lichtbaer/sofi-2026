"""Ortssuche gegen die eigene Datenbank.

Der Bestand kommt einmalig aus dem GeoNames-Dump (siehe
``scripts/seed_geonames.py``). Zur Laufzeit wird kein fremder Dienst befragt —
das ist der Grund, warum hier nicht einfach Nominatim aufgerufen wird: jede
Tastatureingabe der Besucher würde sonst an einen Dritten abfließen.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import connection
from ..normalize import search_keys


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    state: str | None
    lat: float
    lon: float
    elevation: int | None
    population: int
    postal_code: str | None
    source: str


#: Präfixsuche über alle Schreibweisen. Ein Ort kann über mehrere Aliase
#: treffen — gewertet wird der beste Treffer, deshalb das ``min`` über den Rang.
#: Bewusst keine Infix-Suche (``%key%``): sie wäre bei 80.000 Orten langsam und
#: liefert für eine Autovervollständigung mehr Rauschen als Nutzen.
_SEARCH_SQL = """
WITH q AS (SELECT %(key)s::text AS key, %(alt)s::text AS alt),
matched AS (
    SELECT a.place_id,
           min(CASE WHEN a.name_key = q.key OR a.name_key_alt = q.alt THEN 0 ELSE 1 END) AS rank
    FROM place_alias a, q
    WHERE a.name_key LIKE q.key || '%%' OR a.name_key_alt LIKE q.alt || '%%'
    GROUP BY a.place_id
),
hits AS (
    SELECT p.name, p.state, p.population, p.elevation, p.geom, m.rank, 'geonames'::text AS source
    FROM matched m JOIN place p ON p.id = m.place_id
    UNION ALL
    SELECT z.name, z.state, 0, NULL::integer, z.geom, 0, 'postal'
    FROM postal_code z, q
    WHERE z.code LIKE q.key || '%%'
)
SELECT h.name, h.state, h.population, h.elevation, h.rank, h.source,
       ST_Y(h.geom::geometry) AS lat,
       ST_X(h.geom::geometry) AS lon,
       (SELECT z.code FROM postal_code z
        WHERE ST_DWithin(z.geom, h.geom, 8000)
        ORDER BY z.geom <-> h.geom LIMIT 1) AS postal_code
FROM hits h
ORDER BY h.rank, h.population DESC, length(h.name), h.name
LIMIT %(limit)s
"""


async def search(query: str, limit: int = 7) -> list[Place]:
    key, alt = search_keys(query)
    if not key:
        return []

    async with connection() as conn:
        rows = await (
            await conn.execute(_SEARCH_SQL, {"key": key, "alt": alt, "limit": limit})
        ).fetchall()

    seen: set[tuple[str, int]] = set()
    places: list[Place] = []
    for row in rows:
        # Ein Ort taucht über Name und PLZ doppelt auf; grob gerastert entdoppeln.
        marker = (row["name"], int(row["lat"] * 100))
        if marker in seen:
            continue
        seen.add(marker)
        places.append(
            Place(
                name=row["name"],
                state=row["state"],
                lat=row["lat"],
                lon=row["lon"],
                elevation=row["elevation"],
                population=row["population"] or 0,
                postal_code=row["postal_code"],
                source=row["source"],
            )
        )
    return places
