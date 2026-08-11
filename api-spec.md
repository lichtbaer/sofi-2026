# Backend-API — SoFi 2026

Basis-Pfad `/api/v1`. Alle Antworten JSON, `Content-Type: application/json`,
Zeitangaben ISO 8601 in UTC. Interaktive Fassung unter `/api/v1/docs`.

Frontend und API laufen hinter demselben Caddy und damit im selben Origin —
kein CORS, keine Anfrage der Besucher an Dritte. Das ist der Grund, warum hier
weder Nominatim noch ein fremder Kachelserver auftaucht: jede Tastatureingabe
im Suchfeld würde sonst abfließen.

Stand: ✅ implementiert · 🔜 geplant

---

## ✅ GET /api/v1/geocode?q=&limit=7

Ortssuche über Name oder Postleitzahl gegen die eigene Datenbank
(GeoNames DE, CC BY 4.0, einmalig eingespielt).

Zwei Eigenheiten der Quelle, die beim Einspielen behandelt werden: ein Teil der
Großstädte steht dort unter dem englischen Exonym („Munich", „Nuremberg"), und
die Verwaltungscodes sind nicht alphabetisch (07 = Nordrhein-Westfalen,
13 = Sachsen, 15 = Thüringen). Angezeigt wird der deutsche Name; gesucht wird
über alle Schreibweisen, mit und ohne Umlaut („Munchen" wie „Muenchen").

```json
{ "results": [
  { "name": "Köln", "state": "Nordrhein-Westfalen", "plz": "50676",
    "lat": 50.93333, "lon": 6.95, "elevation": 58,
    "population": 1024621, "source": "geonames" } ] }
```

## ✅ GET /api/v1/circumstances?lat=&lon=&elevation=0

Kontaktzeiten C1/C4, Maximum, Bedeckungsgrad, Sonnenhöhe und Azimut.

Dieselbe Rechnung läuft in `frontend/eclipse.js` im Browser und ist dort
schneller als jeder Roundtrip — das bleibt der Hauptweg. Serverseitig wird sie
für die Standortbewertung und die Wolkenauswertung zur *lokalen* Maximumszeit
gebraucht. Damit die beiden Implementierungen nicht auseinanderlaufen, prüft
`backend/tests/test_eclipse.py` sie gegen gemeinsame Stützstellen.

```json
{ "lat": 50.9375, "lon": 6.9603, "visible": true,
  "obscuration": 0.8824, "magnitude": 0.9008,
  "maximum": { "time": "2026-08-12T18:12:44.363Z", "altitude": 5.97, "azimuth": 286.17 },
  "c1": { "time": "2026-08-12T17:18:32.879Z", "altitude": 14.35, "azimuth": 275.93 },
  "c4": { "time": "2026-08-12T19:04:12.774Z", "altitude": -1.59, "azimuth": 296.06 },
  "sunset": "2026-08-12T18:58:52.571Z", "ends_at_sunset": true }
```

## ✅ GET /api/v1/clouds?lat=&lon=

Wolkenprognose aus ICON-D2 (DWD Open Data, 0,02° ≈ 2,2 km, 48 h Vorlauf, alle
3 h ein neuer Lauf), ausgewertet zur **lokalen** Maximumszeit — die liegt
bundesweit zwischen 18:05 und 18:17 UTC und unterscheidet sich von Ort zu Ort.

Vier Schichten statt nur Gesamtbedeckung, weil das bei 2–7° Sonnenhöhe den
Unterschied macht: `high` sind Zirren ab 400 hPa, durch die die Sichel sichtbar
bleibt, `low` ist Bewölkung unter 800 hPa, die die Beobachtung beendet.
`obstruction` fasst das heuristisch zusammen (Gewichte 1,0 / 0,85 / 0,45,
multiplikativ überlagert) — die Rohwerte stehen daneben, wer anders gewichten
will, kann das.

```json
{ "lat": 52.52, "lon": 13.405,
  "forecast": {
    "model": "icon-d2", "run_at": "2026-08-11T06:00:00Z",
    "maximum_at": "2026-08-12T18:08:19.523Z",
    "at_maximum": { "valid_at": "2026-08-12T18:08:19.523Z",
                    "total": 0.224, "low": 0.224, "mid": 0.0, "high": 0.0,
                    "obstruction": 0.224 },
    "series": [ { "valid_at": "2026-08-12T16:00:00Z", "total": 0.27, "low": 0.0,
                  "mid": 0.0, "high": 0.27, "obstruction": 0.122 } ]
  },
  "climatology": null }
```

`forecast` ist `null`, solange kein Lauf eingespielt ist. `climatology`
(CM SAF) fehlt noch — siehe unten.

## ✅ GET /api/v1/clouds/overlays

Verzeichnis der verfügbaren Kartenoverlays des jüngsten Laufs.

```json
{ "overlays": [
  { "variable": "clct", "valid_at": "2026-08-12T18:00:00Z",
    "run_at": "2026-08-11T06:00:00Z", "model": "icon-d2",
    "url": "/api/v1/clouds/overlay.png?variable=clct&valid_at=2026-08-12T18:00:00Z" } ] }
```

## ✅ GET /api/v1/clouds/overlay.png?variable=&valid_at=&bbox=

Das Feld als PNG, Vorgabe-Ausschnitt Deutschland (≈ 492 × 416 px, ~50 kB).
Der Graukanal trägt den Wert direkt in Prozent (0…100), Alpha 0 heißt „keine
Daten". Eingefärbt wird im Frontend — die Farbwahl gehört ins Design, nicht in
die API.

Antwortkopf `X-Image-Bounds: lat_min,lon_min,lat_max,lon_max` nennt die
*tatsächlich* getroffenen Gitterkanten; sie weichen von der angefragten Box um
bis zu eine Maschenweite ab und gehören so an Leaflet übergeben.

## ✅ GET /api/v1/health

```json
{ "status": "ok", "database": true, "forecast_run": "2026-08-11T06:00:00Z" }
```

---

## 🔜 GET /api/v1/elevation?lat=&lon=

Geländehöhe für die Beobachterhöhe in der Kontaktzeitberechnung.
Geplant aus Copernicus GLO-30 als lokales COG.

## 🔜 GET /api/v1/horizon?lat=&lon=&observerHeight=1.6

Horizontprofil. Die Spec sah ursprünglich 360° in 1°- bzw. 0,25°-Schritten vor
— das ist zehnfacher Overkill: der Azimut der Sonne liegt im Maximum
bundesweit zwischen 285° und 290°, über den ganzen Verlauf von C1 bis zum
Untergang zwischen etwa 275° und 300°, und die Höhe bleibt unter 15°.
Gebraucht wird ein Sektor, kein Vollkreis. Damit fällt auch die asynchrone
Job-Mechanik (`202 Accepted`) weg: die Auswertung eines 30°-Sektors aus einem
30-m-Raster liegt im Millisekundenbereich.

Wichtiger als die Auflösung ist die Datenquelle. Bei 2–7° Sonnenhöhe dominiert
das Nahfeld alles:

| Hindernis | Elevation |
| --- | --- |
| 5 m Hecke in 150 m | 1,9° — verdeckt München im Maximum |
| 20 m Baumreihe in 150 m | 7,6° — verdeckt ganz Deutschland |
| Berg 800 m höher in 40 km (mit Krümmung, k = 0,13) | 1,0° |

Das Fernfeld bis 200 km trägt also rund 1° bei, eine Baumreihe am Feldrand das
Achtfache. Ohne DOM1 (Gebäude und Bewuchs) ist ein Horizontprofil für diese
Finsternis von begrenztem Wert — und DOM1 liegt pro Bundesland in eigenen
Formaten und Größenordnungen vor. Bis dahin ist die ehrlichere Auskunft ein
Hinweis „prüfe deinen Westhorizont selbst" statt eines Scores, der die
Baumreihe nicht kennt.

## 🔜 GET /api/v1/clouds — Feld `climatology`

Wahrscheinlichkeit klaren Himmels am 12. August, 18–19 UTC, aus rund 20 Jahren
Satellitenbeobachtung (CM SAF / EUMETSAT CLAAS). Einmalige Offline-Rechnung,
Ergebnis ist ein kleines Raster — kein Dienst zur Laufzeit.

## 🔜 GET /api/v1/sites?lat=&lon=&radiusKm=&limit=20

Bewertete Standorte im Umkreis, absteigend nach `score`, mit aufgeschlüsselten
Teilwerten. Gewichtung: Horizontfreiheit 0,42 · Wolken 0,25 · Bedeckungsgrad
0,18 · Zugänglichkeit 0,15. Hängt an `/horizon`.

## 🔜 POST /api/v1/spots

Eigener Beobachtungsort, speichern und teilen, Bearbeitung über ein
zurückgegebenes `editToken`. Nutzergenerierte Inhalte am Ereignistag brauchen
Rate-Limit und eine Moderationsentscheidung — bewusst zuletzt.

---

## Fehler

```json
{ "detail": "kein Feld clct für 2026-08-12T03:00:00Z" }
```

`400` fehlerhafte Parameter · `404` nicht vorhanden · `422` Validierung
(FastAPI) · `503` Datenbank nicht erreichbar.

## Nicht im Backend

Die Isolinien der Bedeckung. `frontend/eclipse.js` rechnet das komplette
0,2°-Raster über Deutschland samt Marching Squares in **83 ms** — ein
Serverdienst dafür wäre langsamer als die Rechnung selbst.
