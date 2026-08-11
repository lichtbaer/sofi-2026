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

    @property
    def icon_dir(self) -> Path:
        return self.data_dir / "icon-d2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
