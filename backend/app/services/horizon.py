"""Horizontprofil aus dem Höhenraster.

Ein Strahl je Azimut, Schritt für Schritt nach außen, und für jeden Punkt der
Winkel, unter dem er über dem Beobachter erscheint. Der größte dieser Winkel
ist der Horizont in dieser Richtung.

Drei Dinge entscheiden über die Brauchbarkeit des Ergebnisses:

**Erdkrümmung und Refraktion.** Über 20 km sinkt der Boden um rund 27 m weg;
ohne diesen Term würde jede Ferne systematisch überhöht. Gerechnet wird mit
dem effektiven Erdradius R/(1−k), k = 0,13 — Standardatmosphäre.

**Ein Mindestabstand.** Bei 30 m Rasterweite ist die Nachbarzelle keine
Umgebung, sondern das eigene Rauschen. Ohne die Sperre bei 90 m meldet fast
jeder Punkt in Deutschland einen Horizont von 3–4°, weil irgendeine
Nachbarzelle zwei Meter höher liegt.

**Die Bodenhöhe des Beobachters.** Genommen wird der Zellwert selbst, nicht
das Minimum eines Umfelds. Das Minimum wäre naheliegend — im
Oberflächenmodell steht, wer im Wald steht, auf der Baumkrone — aber es
zerstört die Zusage unten: auf einem Gipfel greift es die Hangschulter und
setzt den Beobachter zu tief. Am Hohen Peißenberg sind das 26 m, und die
umliegende Kuppe erscheint dann als 15°-Wand, wo in Wirklichkeit ein
Rundblick ist. Ein zu tief angesetzter Beobachter erzeugt ein falsches
``blocked`` — und genau das darf nicht passieren.

Der Preis: wer unter Bäumen steht, wird auf die Krone gesetzt und das
Ergebnis ist zu optimistisch. Das ist die verträgliche Richtung — aber es
heißt, dass ein Standpunkt im Wald zu gut wegkommt, und das gehört in den
Text an der Oberfläche.

Ein Hinweis „hier stehen vermutlich Bäume" wäre naheliegend und ist hier
bewusst *nicht* eingebaut. Jedes Maß dafür — Abstand zum Umfeldminimum,
Aufragen über die ausgleichende Ebene — misst lokale Konvexität, und ein
scharfer Gipfel ist genauso konvex wie eine Baumkrone. Am Hohen Peißenberg
schlägt beides an. Eine Warnung, die ausgerechnet auf den besten
Aussichtspunkten feuert, verschweigt mehr, als sie meldet.

── Der Fehler bleibt einseitig ──────────────────────────────────────────────

GLO-30 ist ein Oberflächenmodell und enthält Bewuchs. Auf Gebäude ist dennoch
kein Verlass — nachgemessen an der Kachel N50/E008: über dem Frankfurter
Bankenviertel liegt der höchste Wert in einem 1,2-km-Feld bei 127 m, der Median
bei 106 m. Das Dach des Commerzbank-Turms steht bei rund 360 m über NN. Ein
259-m-Hochhaus ist also nicht in den Daten. Die Georeferenzierung der Messung
ist gegengeprüft: Großer Feldberg 871 m, Kachelmaximum 885 m am Gipfel.

Warum, lässt sich aus einer Kachel nicht beweisen. Naheliegend ist nicht
„herausgerechnet", sondern „nie gemessen": TanDEM-X ist ein interferometrisches
Radar, dichte Hochhausbebauung erzeugt Layover und Radarschatten, die
betroffenen Zellen werden zu Datenlücken, und deren Füllung interpoliert aus
der Umgebung. Für flache Bebauung ist ungeprüft, was ankommt — ein Schnitt über
ein Dorf in der Wetterau war nicht auswertbar, weil dort 32 m Geländeanstieg
auf 3 km jeden Objektbeitrag überdecken.

Unabhängig davon greift die Flächenmittelung: Eine 5 m hohe, 3 m breite Hecke
hebt ihre 30-m-Zelle um 0,5 m an, eine 20 m hohe und 10 m breite Baumreihe um
6,7 m. Das Signal wird gedämpft, der Höhenfehler des Rasters nicht — deshalb
holt auch ein kleinerer Mindestabstand als die 90 m oben die Information nicht
zurück. Sie steckt nicht in den Daten.

Was fehlt, verdeckt zusätzlich — nie weniger. Daraus folgt die Semantik, die
``verdict`` liefert:

* ``blocked`` — der Horizont steht bereits über der Sonne. Das ist eine
  belastbare Aussage: bessere Daten können nur mehr verdecken.
* ``clear`` — die Sonne steht frei, **soweit Gelände und Bewuchs reichen**.
  Das ist eine Obergrenze, keine Zusage. ``clearance`` beziffert, wieviel
  unmodelliertes Nahfeld das Urteil noch verträgt: unter etwa zwei Grad kippt
  eine einzelne Baumreihe das Ergebnis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..config import Settings
from ..eclipse import local_circumstances
from .dem import DemStore

EARTH_RADIUS_M = 6_371_000.0
#: Grenze zwischen Nah- und Fernfeld für die Aufschlüsselung im Ergebnis.
NEAR_FIELD_LIMIT_M = 2_000
#: Unter dieser Reserve genügt ein einzelnes unmodelliertes Hindernis.
TIGHT_CLEARANCE_DEG = 2.0


class DemNotReady(RuntimeError):
    """Das Höhenraster ist noch nicht vollständig eingespielt."""


@dataclass(frozen=True, slots=True)
class Profile:
    lat: float
    lon: float
    ground: float
    observer_height: float
    azimuths: np.ndarray
    elevations: np.ndarray
    elevations_far: np.ndarray

    def at(self, azimuth: float) -> float:
        return float(np.interp(azimuth, self.azimuths, self.elevations))

    def at_far(self, azimuth: float) -> float:
        return float(np.interp(azimuth, self.azimuths, self.elevations_far))


@dataclass(frozen=True, slots=True)
class Evaluation:
    profile: Profile
    sun_altitude: float
    sun_azimuth: float
    horizon: float
    horizon_far: float
    clearance: float
    verdict: str
    tight: bool

    @property
    def near_field_gain(self) -> float:
        """Wieviel das Nahfeld über das Fernfeld hinaus beiträgt."""
        return max(0.0, self.horizon - self.horizon_far)


def _metres_per_degree(lat: float) -> tuple[float, float]:
    """WGS84-Näherung. Ein fester Wert von 111 320 m wäre auf 20 km um 20 m daneben."""
    phi = math.radians(lat)
    per_lat = 111_132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    per_lon = 111_412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    return per_lat, per_lon


def _observer_ground(store: DemStore, lat: float, lon: float) -> float:
    """Standhöhe: der Zellwert selbst. Siehe Modulkopf, warum nicht das Minimum."""
    here = store.sample(np.array([lat]), np.array([lon]))[0]
    if not np.isfinite(here):
        raise DemNotReady("keine Höhendaten an diesem Punkt")
    return float(here)


def compute(
    store: DemStore,
    settings: Settings,
    lat: float,
    lon: float,
    observer_height: float = 1.6,
) -> Profile:
    """Horizontprofil über den konfigurierten Azimutsektor."""
    if not store.ready:
        raise DemNotReady("Höhenraster noch nicht vollständig")

    ground = _observer_ground(store, lat, lon)
    eye = ground + observer_height

    azimuths = np.arange(
        settings.horizon_azimuth_from,
        settings.horizon_azimuth_to + 1e-9,
        settings.horizon_azimuth_step,
    )
    # Fein im Nahfeld, grob in der Ferne. Der Schritt muss kleiner sein als
    # das, was er auflösen soll — im Nahfeld ist das die Rasterzelle, in 20 km
    # Entfernung deckt eine Zelle dagegen längst weniger als ein Strahlabstand
    # ab. Gleichmäßig fein zu tasten kostete das Vierfache für nichts.
    near_from = settings.horizon_min_distance_m
    far_from = max(NEAR_FIELD_LIMIT_M, near_from)
    distances = np.concatenate([
        np.arange(near_from, min(NEAR_FIELD_LIMIT_M, settings.horizon_max_distance_m + 1),
                  settings.horizon_step_m, dtype=np.float64),
        np.arange(far_from, settings.horizon_max_distance_m + 1,
                  settings.horizon_step_m * 5, dtype=np.float64),
    ])

    per_lat, per_lon = _metres_per_degree(lat)
    angle = np.radians(azimuths)[:, None]
    span = distances[None, :]

    sample_lat = lat + span * np.cos(angle) / per_lat
    sample_lon = lon + span * np.sin(angle) / per_lon
    heights = store.sample(sample_lat.ravel(), sample_lon.ravel()).reshape(sample_lat.shape)

    # Scheinbares Absinken durch Erdkrümmung, gedämpft durch Refraktion.
    effective_radius = EARTH_RADIUS_M / (1.0 - settings.horizon_refraction_k)
    drop = span * span / (2.0 * effective_radius)
    elevation = np.degrees(np.arctan2(heights - eye - drop, span))

    # Fehlende Zellen zählen nicht als Hindernis, sondern gar nicht.
    # Der Wert wird bewusst *nicht* auf null geklemmt: von einer Höhe aus
    # liegt der Horizont durch die Kimmtiefe unter dem Auge, vom Feldberg ins
    # Rheintal um mehr als zwei Grad. Eine Klemme machte daraus einen zu hohen
    # Horizont — also eine zu kleine Reserve, also ein zu strenges Urteil.
    # Streng ist hier die verbotene Richtung.
    elevation = np.where(np.isnan(elevation), -np.inf, elevation)
    far_only = np.where(span >= NEAR_FIELD_LIMIT_M, elevation, -np.inf)

    def collapse(field: np.ndarray) -> np.ndarray:
        highest = field.max(axis=1)
        # Eine Richtung ganz ohne Daten hat keinen Horizont, nur keine Auskunft.
        return np.where(np.isfinite(highest), highest, np.nan)

    return Profile(
        lat=lat,
        lon=lon,
        ground=ground,
        observer_height=observer_height,
        azimuths=azimuths,
        elevations=collapse(elevation),
        elevations_far=collapse(far_only),
    )


def evaluate(
    store: DemStore,
    settings: Settings,
    lat: float,
    lon: float,
    observer_height: float = 1.6,
) -> Evaluation:
    """Horizont plus Sonnenstand im Maximum, samt Urteil.

    Der Sonnenstand kommt aus derselben Rechnung wie ``/circumstances`` und
    ``/clouds`` — die lokale Maximumszeit unterscheidet sich von Ort zu Ort.
    """
    profile = compute(store, settings, lat, lon, observer_height)
    circumstances = local_circumstances(lat, lon, profile.ground)

    sun_altitude = circumstances.maximum.altitude
    sun_azimuth = circumstances.maximum.azimuth
    horizon = profile.at(sun_azimuth)
    far = profile.at_far(sun_azimuth)
    if not math.isfinite(horizon):
        raise DemNotReady("keine Höhendaten in Richtung der Sonne")
    clearance = sun_altitude - horizon

    return Evaluation(
        profile=profile,
        sun_altitude=sun_altitude,
        sun_azimuth=sun_azimuth,
        horizon=horizon,
        horizon_far=far,
        clearance=clearance,
        verdict="blocked" if clearance <= 0 else "clear",
        tight=0 < clearance < TIGHT_CLEARANCE_DEG,
    )
