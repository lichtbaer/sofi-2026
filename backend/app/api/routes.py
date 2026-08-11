"""HTTP-Schnittstelle. Alle Pfade unter ``/api/v1``."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import connection
from ..eclipse import local_circumstances
from ..services import clouds as clouds_service
from ..services import geocode as geocode_service

router = APIRouter(prefix="/api/v1")

Latitude = Query(..., ge=-90, le=90, description="Breite in Grad")
Longitude = Query(..., ge=-180, le=180, description="Länge in Grad")


# ── Betrieb ─────────────────────────────────────────────────────────────────

class Health(BaseModel):
    status: str
    database: bool
    forecast_run: datetime | None = None


@router.get("/health", response_model=Health)
async def health() -> Health:
    try:
        async with connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT max(run_at) AS run_at FROM forecast_run WHERE finished_at IS NOT NULL"
                )
            ).fetchone()
    except Exception:
        return Health(status="degraded", database=False)
    return Health(status="ok", database=True, forecast_run=row["run_at"])


# ── Ortssuche ───────────────────────────────────────────────────────────────

class PlaceOut(BaseModel):
    name: str
    state: str | None = None
    plz: str | None = None
    lat: float
    lon: float
    elevation: int | None = None
    population: int = 0
    source: str


class GeocodeOut(BaseModel):
    results: list[PlaceOut]


@router.get("/geocode", response_model=GeocodeOut)
async def geocode(
    q: str = Query(..., min_length=1, max_length=80, description="Ortsname oder Postleitzahl"),
    limit: int = Query(7, ge=1, le=25),
) -> GeocodeOut:
    places = await geocode_service.search(q, limit)
    return GeocodeOut(
        results=[
            PlaceOut(
                name=p.name,
                state=p.state,
                plz=p.postal_code,
                lat=p.lat,
                lon=p.lon,
                elevation=p.elevation,
                population=p.population,
                source=p.source,
            )
            for p in places
        ]
    )


# ── Lokale Umstände ─────────────────────────────────────────────────────────

class ContactOut(BaseModel):
    time: datetime
    altitude: float
    azimuth: float


class CircumstancesOut(BaseModel):
    lat: float
    lon: float
    visible: bool
    obscuration: float = Field(..., description="Bedeckter Flächenanteil der Sonne, 0…1")
    magnitude: float
    maximum: ContactOut
    c1: ContactOut | None = None
    c4: ContactOut | None = None
    sunset: datetime | None = None
    ends_at_sunset: bool = False


@router.get("/circumstances", response_model=CircumstancesOut)
async def circumstances(
    lat: float = Latitude,
    lon: float = Longitude,
    elevation: float = Query(0.0, ge=-500, le=5000, description="Höhe des Beobachters in Metern"),
) -> CircumstancesOut:
    """Kontaktzeiten und Maximum.

    Dieselbe Rechnung läuft im Browser (``frontend/eclipse.js``) und ist dort
    schneller. Serverseitig steht sie für Clients ohne JavaScript und für die
    Standortbewertung bereit.
    """
    c = local_circumstances(lat, lon, elevation)

    def contact(state) -> ContactOut:
        return ContactOut(time=state.time, altitude=state.altitude, azimuth=state.azimuth)

    return CircumstancesOut(
        lat=lat,
        lon=lon,
        visible=c.visible,
        obscuration=c.maximum.obscuration,
        magnitude=c.maximum.magnitude,
        maximum=contact(c.maximum),
        c1=contact(c.c1) if c.c1 else None,
        c4=contact(c.c4) if c.c4 else None,
        sunset=c.sunset,
        ends_at_sunset=c.ends_at_sunset,
    )


# ── Wolken ──────────────────────────────────────────────────────────────────

class CloudSampleOut(BaseModel):
    valid_at: datetime
    total: float | None = None
    low: float | None = None
    mid: float | None = None
    high: float | None = None
    obstruction: float | None = Field(
        None, description="Heuristischer Verdeckungsgrad der tiefstehenden Sonne, 0…1"
    )


class ForecastOut(BaseModel):
    model: str
    run_at: datetime
    maximum_at: datetime
    at_maximum: CloudSampleOut
    series: list[CloudSampleOut]


class CloudsOut(BaseModel):
    lat: float
    lon: float
    forecast: ForecastOut | None = None
    climatology: None = Field(None, description="CM SAF, noch nicht eingespielt")


def _sample_out(sample: clouds_service.CloudSample) -> CloudSampleOut:
    # Die Quelle ist auf 1 % quantisiert; drei Nachkommastellen sind schon
    # großzügig und ersparen dem Frontend Werte wie 4.77e-14.
    r = lambda v: None if v is None else round(v, 3)  # noqa: E731
    return CloudSampleOut(
        valid_at=sample.valid_at,
        total=r(sample.total),
        low=r(sample.low),
        mid=r(sample.mid),
        high=r(sample.high),
        obstruction=r(sample.obstruction),
    )


@router.get("/clouds", response_model=CloudsOut)
async def clouds(lat: float = Latitude, lon: float = Longitude) -> CloudsOut:
    forecast = await clouds_service.point_forecast(lat, lon)
    if forecast is None:
        return CloudsOut(lat=lat, lon=lon)
    return CloudsOut(
        lat=lat,
        lon=lon,
        forecast=ForecastOut(
            model=forecast.model,
            run_at=forecast.run_at,
            maximum_at=forecast.maximum_at,
            at_maximum=_sample_out(forecast.at_maximum),
            series=[_sample_out(s) for s in forecast.series],
        ),
    )


class OverlayOut(BaseModel):
    variable: str
    valid_at: datetime
    run_at: datetime
    model: str
    url: str


class OverlaysOut(BaseModel):
    overlays: list[OverlayOut]


@router.get("/clouds/overlays", response_model=OverlaysOut)
async def overlays() -> OverlaysOut:
    fields = await clouds_service.current_fields()
    return OverlaysOut(
        overlays=[
            OverlayOut(
                variable=f.variable,
                valid_at=f.valid_at,
                run_at=f.run_at,
                model=f.model,
                url=(
                    f"/api/v1/clouds/overlay.png?variable={f.variable}"
                    f"&valid_at={f.valid_at.isoformat().replace('+00:00', 'Z')}"
                ),
            )
            for f in fields
        ]
    )


@router.get(
    "/clouds/overlay.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def overlay_png(
    variable: str = Query("clct", pattern="^(clct|clcl|clcm|clch)$"),
    valid_at: datetime = Query(..., description="Gültigkeitszeitpunkt in UTC"),
    bbox: str | None = Query(
        None, description="lat_min,lon_min,lat_max,lon_max — Vorgabe ist Deutschland"
    ),
) -> Response:
    """Bewölkungsfeld als PNG.

    Der Graukanal trägt den Wert in Prozent (0…100), Alpha 0 heißt „keine
    Daten". Die Einfärbung passiert im Frontend.
    """
    settings = get_settings()
    bounds = settings.germany_bbox
    if bbox:
        try:
            parsed = tuple(float(v) for v in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(400, "bbox nicht lesbar") from exc
        if len(parsed) != 4:
            raise HTTPException(400, "bbox braucht vier Werte")
        bounds = parsed  # type: ignore[assignment]

    fields = await clouds_service.current_fields()
    match = next((f for f in fields if f.variable == variable and f.valid_at == valid_at), None)
    if match is None:
        raise HTTPException(404, f"kein Feld {variable} für {valid_at.isoformat()}")

    try:
        png, actual = clouds_service.render_overlay(match, bounds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return Response(
        content=png,
        media_type="image/png",
        headers={
            # Leaflet braucht die tatsächlichen Kanten, nicht die angefragten.
            "X-Image-Bounds": ",".join(f"{v:.6f}" for v in actual),
            "X-Run-At": match.run_at.isoformat(),
            "Cache-Control": "public, max-age=600",
        },
    )
