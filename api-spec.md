# Backend-API — SoFi 2026

Das Frontend rechnet Kontaktzeiten, Bedeckungsgrade und Isolinien selbst (Besselsche
Elemente, NASA Five Millennium Canon). Das Backend liefert alles, was Geodaten oder
Rechenlast braucht. Alle Antworten JSON, `Content-Type: application/json`.

## GET /api/geocode?q=&limit=7
Ortssuche über Name oder PLZ. Quelle: BKG-Geokodierungsdienst oder Nominatim,
auf Deutschland begrenzt (`countrycodes=de`).

```json
{ "results": [
  { "name": "Kassel", "plz": "34117", "state": "Hessen",
    "lat": 51.3127, "lon": 9.4797, "elevation": 167, "source": "bkg" } ] }
```

## GET /api/elevation?lat=&lon=
Geländehöhe aus DGM1/DGM10. Wird für die Höhe des Beobachters in der
Kontaktzeitberechnung gebraucht.

```json
{ "lat": 51.3127, "lon": 9.4797, "elevation": 167.4, "model": "dgm1" }
```

## GET /api/horizon?lat=&lon=&observerHeight=1.6
Horizontprofil, berechnet mit **HORAYZON**. Nahfeld (< 2 km) aus **DOM1**
(Oberflächenmodell, enthält Gebäude und Bewuchs), Fernfeld bis 200 km aus **DGM**
(Geländemodell, 10 m). Erdkrümmung und Refraktion (k = 0,13) berücksichtigt.

Antwort: Horizonthöhe in Grad je Azimut, 1°-Raster ab Nord, im Uhrzeigersinn.

```json
{ "lat": 51.7991, "lon": 10.6156, "observerHeight": 1.6,
  "resolution": 1.0,
  "nearField": { "model": "dom1", "radius_m": 2000 },
  "farField":  { "model": "dgm10", "radius_m": 200000 },
  "horizon": [0.4, 0.4, 0.5, "… 360 Werte …"],
  "computed": "2026-06-01T10:00:00Z" }
```

Caching: Ergebnis ist zeitunabhängig → dauerhaft cachebar, Schlüssel auf
6 Nachkommastellen gerundete Koordinate. Rechenzeit pro Punkt ~1–3 s, deshalb
asynchron mit `202 Accepted` + `Location: /api/horizon/jobs/{id}` bei Cache-Miss.

## GET /api/clouds?lat=&lon=
Zwei Werte, klar getrennt:
- `climatology`: Wahrscheinlichkeit klaren Himmels am 12. August, 18–19 UTC,
  aus 20 Jahren Satellitenbeobachtung (CM SAF / EUMETSAT).
- `forecast`: erst ab 7 Tagen vor dem Ereignis gefüllt, sonst `null`
  (ICON-D2 Gesamtbedeckung zur Maximumszeit).

```json
{ "climatology": { "clearSkyProbability": 0.52, "source": "cmsaf-claas3", "years": 20 },
  "forecast": { "cloudCover": 0.35, "runTime": "2026-08-11T00:00:00Z", "model": "icon-d2" } }
```

## GET /api/sites?lat=&lon=&radiusKm=&limit=20
Bewertete Beobachtungsstandorte im Umkreis, absteigend nach `score`.
Der Score ist gewichtet: Horizontfreiheit 0,42 · Wolkenklimatologie 0,25 ·
Bedeckungsgrad 0,18 · Zugänglichkeit 0,15. Die Teilwerte werden mitgeliefert,
damit das Frontend die Aufschlüsselung zeigen kann.

```json
{ "sites": [
  { "id": "brocken", "name": "Brocken", "region": "Harz, Sachsen-Anhalt",
    "lat": 51.7991, "lon": 10.6156, "elevation": 1141, "distanceKm": 248,
    "score": 91,
    "factors": {
      "horizonClearance": { "value": 2.7, "unit": "deg", "score": 0.80 },
      "clearSky":         { "value": 0.38, "score": 0.38 },
      "obscuration":      { "value": 0.861, "score": 0.46 },
      "access":           { "value": "frei", "score": 1.0 } },
    "accessNote": "Nationalpark, Brockenbahn bis zum Gipfel, kein Pkw-Zugang.",
    "horizonUrl": "/api/horizon?lat=51.7991&lon=10.6156" } ] }
```

## POST /api/spots
Eigener Beobachtungsort, speichern und teilen. Antwort enthält eine kurze
Teil-URL. Keine Anmeldung, Bearbeitung über das zurückgegebene `editToken`.

```json
// Request
{ "name": "Feldrand bei Nauheim", "lat": 49.93, "lon": 8.45, "note": "Parken am Waldweg" }
// Response
{ "id": "k7m2qa", "url": "https://sofi2026.de/s/k7m2qa", "editToken": "…" }
```

## Fehler
```json
{ "error": { "code": "OUT_OF_COVERAGE",
             "message": "Für diese Koordinate liegt kein DOM1-Raster vor." } }
```
`OUT_OF_COVERAGE` · `RATE_LIMITED` · `COMPUTING` (Job läuft noch) · `BAD_REQUEST`.

## Nicht im Backend
Kontaktzeiten C1–C4, Bedeckungsgrad, Sonnenhöhe/Azimut und die Isolinien der
Bedeckung. Das rechnet `eclipse.js` im Browser aus den Besselschen Elementen —
schneller als jeder Roundtrip und offline verfügbar.
