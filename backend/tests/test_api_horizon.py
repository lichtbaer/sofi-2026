"""Vertrag der Horizont- und Höhenrouten.

Geprüft wird der Weg durch FastAPI und Pydantic, nicht die Geometrie — die
steht in ``test_horizon.py``. Interessant sind hier drei Dinge, an denen ein
Fehler still bliebe: dass ein fehlendes Höhenraster einen 503 gibt statt einer
erfundenen Zahl, dass ``null`` im Profil die Serialisierung übersteht, und
dass ``verdict`` genau die beiden Werte annimmt, auf denen die Textbausteine
im Frontend aufsetzen.

Der Verbindungspool wird nicht geöffnet: die TestClient-Instanz läuft ohne
``lifespan``, und keine der beiden Routen fasst die Datenbank an.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app

client = TestClient(app)


class StubStore:
    """Ebene auf 100 m mit einer 40 m hohen Wand ab 300 m Entfernung."""

    def __init__(self, ready=True, blank=False):
        self.ready = ready
        self.blank = blank

    def sample(self, lat, lon):
        lat = np.asarray(lat, dtype=float)
        if self.blank:
            return np.full(lat.shape, np.nan)
        lon = np.asarray(lon, dtype=float)
        distance = np.hypot((lat - 50.0) * 111_229.0, (lon - 10.0) * 71_700.0)
        return np.where(distance >= 300.0, 140.0, 100.0)


@pytest.fixture
def store(monkeypatch):
    def install(**kwargs):
        stub = StubStore(**kwargs)
        monkeypatch.setattr(routes.dem_service, "get_store", lambda settings: stub)
        return stub

    return install


def test_horizon_liefert_profil_und_urteil(store):
    store()
    response = client.get("/api/v1/horizon", params={"lat": 50.0, "lon": 10.0})
    assert response.status_code == 200
    body = response.json()

    assert body["source"]["kind"] == "dsm"
    assert body["source"]["contains_vegetation"] is True
    assert body["source"]["contains_buildings"] is False
    assert body["observer"] == {"ground": 100.0, "height": 1.6}

    span = body["azimuth"]
    expected = round((span["end"] - span["start"]) / span["step"]) + 1
    assert len(body["elevation"]) == expected

    maximum = body["at_maximum"]
    assert maximum["verdict"] in {"blocked", "clear"}
    # 40 m Wand in 300 m sind rund 7,3° — die Sonne steht bundesweit unter 8°.
    assert maximum["horizon"] == pytest.approx(7.3, abs=0.5)
    assert maximum["verdict"] == "blocked"
    assert maximum["clearance"] < 0
    assert maximum["horizon_far"] < maximum["horizon"]


def test_freie_sicht_ist_knapp_markiert(store):
    """Ohne Hindernis bleibt viel Reserve — ``tight`` darf dann nicht gesetzt sein."""
    monkeypatched = store()
    monkeypatched.sample = lambda lat, lon: np.full(np.asarray(lat, dtype=float).shape, 100.0)
    body = client.get("/api/v1/horizon", params={"lat": 50.0, "lon": 10.0}).json()
    assert body["at_maximum"]["verdict"] == "clear"
    assert body["at_maximum"]["clearance"] > 2.0
    assert body["at_maximum"]["tight"] is False


def test_horizon_ohne_raster_gibt_503_statt_einer_zahl(store):
    store(ready=False)
    response = client.get("/api/v1/horizon", params={"lat": 50.0, "lon": 10.0})
    assert response.status_code == 503


def test_horizon_ausserhalb_des_rasters_gibt_503(store):
    store(blank=True)
    assert client.get("/api/v1/horizon", params={"lat": 50.0, "lon": 10.0}).status_code == 503


def test_elevation(store):
    store()
    body = client.get("/api/v1/elevation", params={"lat": 50.0, "lon": 10.0}).json()
    assert body["elevation"] == 100.0
    assert body["source"]["model"] == "copernicus-glo30"


def test_elevation_ohne_raster_gibt_503(store):
    store(ready=False)
    assert client.get("/api/v1/elevation", params={"lat": 50.0, "lon": 10.0}).status_code == 503


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 95.0, "lon": 10.0},
        {"lat": 50.0, "lon": 200.0},
        {"lat": 50.0, "lon": 10.0, "observerHeight": -1},
        {"lat": 50.0},
    ],
)
def test_ungueltige_eingaben(store, params):
    store()
    assert client.get("/api/v1/horizon", params=params).status_code == 422
