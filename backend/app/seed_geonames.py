"""Einmaliges Einspielen der Ortsdaten aus dem GeoNames-Dump.

    docker compose run --rm api python -m app.seed_geonames

Quelle: https://download.geonames.org (CC BY 4.0). Der Dump wird beim Seeden
geholt und danach nie wieder angefasst — im Betrieb geht keine Anfrage nach
draußen, damit keine Tastatureingabe der Besucher bei Dritten landet.

Zwei Eigenheiten der Quelle, die man kennen muss:

* Der Hauptname ist teils das englische Exonym — „Munich", „Nuremberg",
  „Brunswick" — während andere Städte deutsch geführt werden. Der Anzeigename
  kommt deshalb aus ``alternatenames`` mit ``isolanguage = de``.
* Die Verwaltungscodes sind nicht alphabetisch: 07 ist Nordrhein-Westfalen,
  13 Sachsen, 15 Thüringen. Die Zuordnung unten wird beim Seeden gegen
  ``admin1CodesASCII.txt`` geprüft.
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections import defaultdict

import httpx
import psycopg

from .config import get_settings
from .normalize import search_keys

log = logging.getLogger("seed")

ADMIN1_CODES_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
ALTERNATE_NAMES_URL = "https://download.geonames.org/export/dump/alternatenames/DE.zip"

#: GeoNames-Verwaltungscode -> Bundesland. Rechts steht die englische
#: Bezeichnung aus admin1CodesASCII.txt, gegen die geprüft wird.
STATES: dict[str, tuple[str, str]] = {
    "01": ("Baden-Württemberg", "Baden-Wurttemberg"),
    "02": ("Bayern", "Bavaria"),
    "03": ("Bremen", "Bremen"),
    "04": ("Hamburg", "Hamburg"),
    "05": ("Hessen", "Hesse"),
    "06": ("Niedersachsen", "Lower Saxony"),
    "07": ("Nordrhein-Westfalen", "North Rhine-Westphalia"),
    "08": ("Rheinland-Pfalz", "Rheinland-Pfalz"),
    "09": ("Saarland", "Saarland"),
    "10": ("Schleswig-Holstein", "Schleswig-Holstein"),
    "11": ("Brandenburg", "Brandenburg"),
    "12": ("Mecklenburg-Vorpommern", "Mecklenburg-Vorpommern"),
    "13": ("Sachsen", "Saxony"),
    "14": ("Sachsen-Anhalt", "Saxony-Anhalt"),
    "15": ("Thüringen", "Thuringia"),
    "16": ("Berlin", "State of Berlin"),
}

#: Bewohnte Orte. Ohne aufgegebene, zerstörte und historische Siedlungen —
#: die stören die Autovervollständigung mehr als sie helfen.
KEEP_FEATURE_CODES = {
    "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLA5", "PPLC", "PPLL", "PPLX",
}


def _fetch(url: str) -> bytes:
    log.info("lade %s", url)
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    return response.content


def _fetch_zip_member(url: str, member: str) -> str:
    with zipfile.ZipFile(io.BytesIO(_fetch(url))) as archive:
        return archive.read(member).decode("utf-8")


def verify_state_codes(admin1_text: str) -> None:
    """Bricht ab, wenn GeoNames die Verwaltungscodes umnummeriert hat.

    Eine stille Verschiebung würde jedem Ort das falsche Bundesland anhängen —
    ein Fehler, den im Frontend niemand als Datenfehler erkennt.
    """
    published = {
        line.split("\t")[0].removeprefix("DE."): line.split("\t")[1]
        for line in admin1_text.splitlines()
        if line.startswith("DE.")
    }
    problems = [
        f"{code}: erwartet {english!r}, veröffentlicht {published.get(code)!r}"
        for code, (_, english) in STATES.items()
        if published.get(code) != english
    ]
    if problems:
        raise SystemExit("Verwaltungscodes stimmen nicht mehr:\n  " + "\n  ".join(problems))
    log.info("16 Verwaltungscodes gegen admin1CodesASCII.txt bestätigt")


def german_names(alternate_text: str) -> tuple[dict[int, str], dict[int, set[str]]]:
    """Deutscher Anzeigename je geonameid und alle deutschen Schreibweisen.

    Spalten: id, geonameid, isolanguage, name, preferred, short, colloquial,
    historic. Bevorzugt wird der als ``preferred`` markierte Name, sonst der
    kurze, sonst der erste. Umgangssprachliches und Historisches fliegt raus.
    """
    preferred: dict[int, str] = {}
    short: dict[int, str] = {}
    first: dict[int, str] = {}
    variants: dict[int, set[str]] = defaultdict(set)

    for line in alternate_text.splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or parts[2] != "de":
            continue
        is_preferred = len(parts) > 4 and parts[4] == "1"
        is_short = len(parts) > 5 and parts[5] == "1"
        is_colloquial = len(parts) > 6 and parts[6] == "1"
        is_historic = len(parts) > 7 and parts[7] == "1"
        if is_colloquial or is_historic:
            continue

        geonames_id, name = int(parts[1]), parts[3].strip()
        if not name:
            continue
        variants[geonames_id].add(name)
        if is_preferred:
            preferred.setdefault(geonames_id, name)
        elif is_short:
            short.setdefault(geonames_id, name)
        else:
            first.setdefault(geonames_id, name)

    display = {**first, **short, **preferred}
    return display, variants


def _seed_places(
    conn: psycopg.Connection,
    text: str,
    display_names: dict[int, str],
    variants: dict[int, set[str]],
) -> tuple[int, int]:
    places = 0
    aliases: list[tuple[int, str, str]] = []

    with conn.cursor().copy(
        "COPY place (id, geonames_id, name, feature_code, state, population, elevation, geom) "
        "FROM STDIN"
    ) as copy:
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 19 or parts[6] != "P" or parts[7] not in KEEP_FEATURE_CODES:
                continue

            geonames_id = int(parts[0])
            dump_name = parts[1].strip()
            if not dump_name:
                continue

            places += 1
            place_id = places
            name = display_names.get(geonames_id, dump_name)
            elevation = parts[15] or parts[16] or ""
            state = STATES.get(parts[10], (None, None))[0]

            copy.write_row(
                (
                    place_id,
                    geonames_id,
                    name,
                    parts[7],
                    state,
                    int(parts[14] or 0),
                    int(elevation) if elevation.lstrip("-").isdigit() else None,
                    f"SRID=4326;POINT({float(parts[5])} {float(parts[4])})",
                )
            )

            spellings = {name, dump_name, parts[2].strip()} | variants.get(geonames_id, set())
            for spelling in spellings:
                if spelling:
                    key, alt = search_keys(spelling)
                    if key:
                        aliases.append((place_id, key, alt))

    unique = sorted(set(aliases))
    with conn.cursor().copy("COPY place_alias (place_id, name_key, name_key_alt) FROM STDIN") as copy:
        for row in unique:
            copy.write_row(row)

    conn.execute("SELECT setval(pg_get_serial_sequence('place', 'id'), %s)", (places,))
    return places, len(unique)


def _seed_postal_codes(conn: psycopg.Connection, text: str) -> int:
    seen: set[tuple[str, str]] = set()
    rows = 0
    with conn.cursor().copy(
        "COPY postal_code (code, name, name_key, state, geom) FROM STDIN"
    ) as copy:
        for line in text.splitlines():
            # Spalten: Land, PLZ, Ort, Bundesland, …, Breite (9), Länge (10), Genauigkeit (11).
            parts = line.split("\t")
            if len(parts) < 11:
                continue
            code, name, lat, lon = parts[1].strip(), parts[2].strip(), parts[9], parts[10]
            if not code or not name or not lat or not lon or (code, name) in seen:
                continue
            seen.add((code, name))
            key, _ = search_keys(name)
            copy.write_row(
                (code, name, key, parts[3] or None, f"SRID=4326;POINT({float(lon)} {float(lat)})")
            )
            rows += 1
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    settings = get_settings()

    verify_state_codes(_fetch(ADMIN1_CODES_URL).decode("utf-8"))
    display_names, variants = german_names(_fetch_zip_member(ALTERNATE_NAMES_URL, "DE.txt"))
    log.info("%d deutsche Anzeigenamen gefunden", len(display_names))

    places_text = _fetch_zip_member(settings.geonames_dump_url, "DE.txt")
    postal_text = _fetch_zip_member(settings.geonames_postal_url, "DE.txt")

    with psycopg.connect(settings.database_url) as conn:
        with conn.transaction():
            conn.execute("TRUNCATE place, place_alias, postal_code RESTART IDENTITY CASCADE")
            places, aliases = _seed_places(conn, places_text, display_names, variants)
            codes = _seed_postal_codes(conn, postal_text)
        for table in ("place", "place_alias", "postal_code"):
            conn.execute(f"ANALYZE {table}")

    log.info(
        "%d Orte, %d Schreibweisen und %d Postleitzahlen eingespielt", places, aliases, codes
    )


if __name__ == "__main__":
    main()
