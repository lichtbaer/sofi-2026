"""Tests für die Horizontrechnung.

Das Höhenraster wird hier synthetisch gestellt: eine Ebene, eine Wand in
bekanntem Abstand, ein Loch ohne Daten. Damit ist die Geometrie geprüft —
Winkel, Erdkrümmung, Mindestabstand — ohne 3 GB Kacheln und ohne Netz.

Der Grund für diese Tests ist nicht Vollständigkeit, sondern Richtung: die
gesamte Semantik im Frontend hängt daran, dass ``blocked`` nie zu früh kommt.
Jede Näherung in ``horizon.py`` muss den Horizont eher zu *niedrig* ansetzen.
Ein Vorzeichenfehler in der Krümmung oder eine zu tief angesetzte Standhöhe
kehrt das um, ohne dass die Zahlen unplausibel aussähen.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.config import Settings
from app.services import horizon as H


class FlatDem:
    """Ebene auf konstanter Höhe, optional mit einer Wand in fester Entfernung.

    Die Wand steht als Ring: ab ``wall_distance_m`` in jeder Richtung. Damit
    ist der erwartete Winkel für jeden Azimut derselbe und leicht von Hand
    nachzurechnen.
    """

    ready = True

    def __init__(self, base=100.0, wall_height=0.0, wall_distance_m=None, lat0=50.0, lon0=10.0):
        self.base = base
        self.wall_height = wall_height
        self.wall_distance_m = wall_distance_m
        self.lat0, self.lon0 = lat0, lon0

    def sample(self, lat, lon):
        lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
        per_lat, per_lon = H._metres_per_degree(self.lat0)
        distance = np.hypot((lat - self.lat0) * per_lat, (lon - self.lon0) * per_lon)
        out = np.full(lat.shape, self.base)
        if self.wall_distance_m is not None:
            out = np.where(distance >= self.wall_distance_m, self.base + self.wall_height, out)
        return out


class EmptyDem:
    ready = True

    def sample(self, lat, lon):
        return np.full(np.asarray(lat, dtype=float).shape, np.nan)


def _settings(**over) -> Settings:
    base = dict(
        horizon_azimuth_from=270.0, horizon_azimuth_to=290.0, horizon_azimuth_step=1.0,
        horizon_min_distance_m=90, horizon_max_distance_m=20_000, horizon_step_m=10,
    )
    return Settings(**{**base, **over})


def test_ebene_liefert_leicht_negativen_horizont():
    """Auf einer Ebene liegt der Horizont durch die Krümmung unter dem Auge."""
    profile = H.compute(FlatDem(), _settings(), 50.0, 10.0, observer_height=1.6)
    assert np.all(profile.elevations < 0)
    # Die Kimmtiefe für 1,6 m Augenhöhe: arctan(sqrt(2h/R_eff)) ≈ 0,038°.
    expected = math.degrees(math.atan(math.sqrt(2 * 1.6 * (1 - 0.13) / 6_371_000)))
    assert profile.elevations.max() == pytest.approx(-expected, abs=0.02)


def test_wand_ergibt_den_erwarteten_winkel():
    """20 m Wand in 150 m: arctan(20/150) minus Krümmung — die 7,6° aus dem README."""
    dem = FlatDem(wall_height=20.0, wall_distance_m=150.0)
    profile = H.compute(dem, _settings(), 50.0, 10.0, observer_height=1.6)
    drop = 150.0**2 / (2 * 6_371_000 / (1 - 0.13))
    expected = math.degrees(math.atan((20.0 - 1.6 - drop) / 150.0))
    assert profile.elevations.max() == pytest.approx(expected, abs=0.1)


def test_mindestabstand_blendet_die_nachbarzelle_aus():
    """Eine Wand innerhalb des Mindestabstands darf nicht zählen.

    Ohne diese Sperre meldet jeder Punkt den Höhenunterschied zur Nachbarzelle
    als Horizont — bei 30 m Rasterweite sind das regelmäßig 3–4°.
    """
    dem = FlatDem(wall_height=50.0, wall_distance_m=40.0)
    weit = H.compute(dem, _settings(horizon_min_distance_m=90), 50.0, 10.0)
    nah = H.compute(dem, _settings(horizon_min_distance_m=20), 50.0, 10.0)
    # Die Wand reicht nach außen, ab 90 m steht sie also weiter — nur flacher:
    # arctan(48,4/90) ≈ 28°, ab 40 m dagegen arctan(48,4/40) ≈ 50°.
    assert weit.elevations.max() == pytest.approx(28.3, abs=1.0)
    assert nah.elevations.max() == pytest.approx(50.4, abs=1.0)


def test_kruemmung_senkt_die_ferne():
    """Gleiche Höhe in 20 km liegt durch die Krümmung deutlich unter dem Auge."""
    dem = FlatDem(wall_height=0.0)
    profile = H.compute(dem, _settings(horizon_min_distance_m=19_000), 50.0, 10.0)
    drop = 20_000.0**2 / (2 * 6_371_000 / (1 - 0.13))
    assert drop == pytest.approx(27.3, abs=1.0)
    assert profile.elevations.max() < -0.05


def test_fernfeld_wird_getrennt_ausgewiesen():
    """Ein Hindernis unter 2 km zählt zum Nahfeld, nicht zum Fernfeld."""
    dem = FlatDem(wall_height=30.0, wall_distance_m=500.0)
    profile = H.compute(dem, _settings(), 50.0, 10.0)
    azimuth = 280.0
    assert profile.at(azimuth) > 2.0
    # Ab 2 km steht dieselbe Wand viel flacher — der Unterschied ist das Nahfeld.
    assert profile.at_far(azimuth) < profile.at(azimuth)


def test_standhoehe_ist_der_zellwert_nicht_das_minimum():
    """Auf einer Kuppe darf der Beobachter nicht auf die Hangschulter rutschen.

    Sonst entsteht ein falsches ``blocked`` — und ``blocked`` wird im Frontend
    als Aussage gerendert, nicht als Obergrenze.
    """
    class Kuppe(FlatDem):
        def sample(self, lat, lon):
            lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
            per_lat, per_lon = H._metres_per_degree(self.lat0)
            d = np.hypot((lat - self.lat0) * per_lat, (lon - self.lon0) * per_lon)
            return 1000.0 - np.minimum(d, 400.0) * 0.1   # 10 % Gefälle, dann flach

    profile = H.compute(Kuppe(), _settings(), 50.0, 10.0)
    assert profile.ground == pytest.approx(1000.0, abs=0.1)
    assert np.all(profile.elevations < 0)          # von der Kuppe geht es nur abwärts


def test_beobachter_im_bewuchs_wird_auf_die_krone_gesetzt():
    """Unter Bäumen kommt die Standhöhe zu hoch heraus — die zulässige Richtung.

    Zu hoch heißt: Horizont zu niedrig, Reserve zu groß, Urteil zu günstig.
    Ein zu tief angesetzter Beobachter erzeugte dagegen ein falsches
    ``blocked``, und das wird als Aussage gerendert.
    """
    class Baum(FlatDem):
        def sample(self, lat, lon):
            lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
            per_lat, per_lon = H._metres_per_degree(self.lat0)
            d = np.hypot((lat - self.lat0) * per_lat, (lon - self.lon0) * per_lon)
            return np.where(d < 20.0, 120.0, 100.0)

    profile = H.compute(Baum(), _settings(), 50.0, 10.0)
    assert profile.ground == pytest.approx(120.0, abs=0.1)
    assert np.all(profile.elevations < 0)


def test_ohne_hoehendaten_wird_abgelehnt():
    with pytest.raises(H.DemNotReady):
        H.compute(EmptyDem(), _settings(), 50.0, 10.0)


def test_unfertiges_raster_wird_abgelehnt():
    class NichtBereit(FlatDem):
        ready = False

    with pytest.raises(H.DemNotReady):
        H.compute(NichtBereit(), _settings(), 50.0, 10.0)
