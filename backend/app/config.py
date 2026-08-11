"""Konfiguration. Alles über Umgebungsvariablen mit Präfix ``SOFI_``."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SOFI_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://sofi:sofi@db:5432/sofi"
    data_dir: Path = Path("/data")

    #: Tag der Finsternis. Steuert, welche Vorhersagezeitpunkte geholt werden.
    event_date: date = date(2026, 8, 12)
    #: Fenster in UTC-Stunden. Das Maximum liegt bundesweit zwischen 18:05 und
    #: 18:17 UTC; die Ränder decken Anfahrt und Sonnenuntergang mit ab.
    event_hours_utc: tuple[int, ...] = (16, 17, 18, 19, 20)

    icon_base_url: str = "https://opendata.dwd.de/weather/nwp/icon-d2/grib"
    icon_variables: tuple[str, ...] = ("clct", "clcl", "clcm", "clch")
    icon_run_hours: tuple[int, ...] = (0, 3, 6, 9, 12, 15, 18, 21)
    #: ICON-D2 reicht 48 h. Weiter zurück brauchen wir gar nicht erst zu suchen.
    icon_max_lead_hours: int = 48
    #: So viele abgeschlossene Läufe bleiben auf der Platte.
    keep_runs: int = 3

    worker_interval_s: int = 600
    http_timeout_s: float = 60.0

    #: Vorgabe-Ausschnitt für Kartenoverlays (lat_min, lon_min, lat_max, lon_max).
    germany_bbox: tuple[float, float, float, float] = (47.0, 5.6, 55.3, 15.4)

    geonames_dump_url: str = "https://download.geonames.org/export/dump/DE.zip"
    geonames_postal_url: str = "https://download.geonames.org/export/zip/DE.zip"

    #: Copernicus DEM GLO-30, offen und ohne Anmeldung auf S3.
    dem_base_url: str = "https://copernicus-dem-30m.s3.amazonaws.com"

    #: Kleinster Abstand, ab dem eine Zelle als Hindernis zählt. Bei 30 m
    #: Rasterweite ist alles darunter das eigene Umfeld, nicht die Umgebung —
    #: ohne diese Sperre meldet jede Nachbarzelle einen Horizont von 3–4°.
    horizon_min_distance_m: int = 90
    #: Reichweite eines Strahls. 800 m Überhöhung in 40 km sind 1,0°; jenseits
    #: davon frisst die Erdkrümmung schneller, als das Gelände wächst.
    horizon_max_distance_m: int = 40_000
    #: Rand, den das Höhenraster über die Deutschland-Box hinaus abdeckt.
    #: Bewusst kleiner als die Strahlreichweite: ein Strahl, der nahe der
    #: Grenze aus dem Raster läuft, endet dort. Das verkürzt sein Fernfeld und
    #: lässt den Horizont eher zu niedrig erscheinen — die unbedenkliche
    #: Richtung. Den Rand auf 40 km zu ziehen kostete zwei Kachelspalten mehr.
    dem_margin_m: int = 20_000
    #: Schrittweite entlang eines Strahls. Kleiner als die Rasterweite, damit
    #: keine Zelle übersprungen wird.
    horizon_step_m: int = 20
    #: Ausgewerteter Azimutsektor. Die Sonne steht von C1 bis zum Untergang
    #: zwischen 275° und 300°; der Rand gibt Luft für die Darstellung.
    horizon_azimuth_from: float = 240.0
    horizon_azimuth_to: float = 330.0
    horizon_azimuth_step: float = 0.25
    #: Refraktionskoeffizient für die scheinbare Erdkrümmung (Standardatmosphäre).
    horizon_refraction_k: float = 0.13

    @property
    def icon_dir(self) -> Path:
        return self.data_dir / "icon-d2"

    @property
    def dem_dir(self) -> Path:
        return self.data_dir / "dem"


@lru_cache
def get_settings() -> Settings:
    return Settings()
