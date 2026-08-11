# Sonnenfinsternis 2026 — Deutschland

Website zur partiellen Sonnenfinsternis am **12. August 2026** in Deutschland.
Kontaktzeiten, Bedeckungsgrade, Isolinien, Wolkenprognose und Standortbewertung.

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `frontend/Sofi.dc.html` | Die Seite: Start, Zeiten & Orte, Beste Standorte, Sicherheit |
| `frontend/eclipse.js` | Finsternisrechnung — Besselsche Elemente, lokale Umstände, Isolinien |
| `frontend/api.js` | Client für die eigene API |
| `frontend/config.js` | Kachelanbieter und API-Basis — die einzigen Betriebsknöpfe |
| `frontend/data.js` | Ersatzdaten: 54 Städte als Rückfall, Standorte und Horizontprofile noch als Mock |
| `frontend/vendor/` | Leaflet, React, Schriften — selbst ausgeliefert |
| `frontend/_ds/` | Design-System *Organic* (Tokens, Komponenten) |
| `backend/` | FastAPI: Ortssuche, Wolkenprognose, lokale Umstände |
| `db/init/` | PostGIS-Schema |
| `web/Caddyfile` | Reverse Proxy, statische Auslieferung, CSP |
| `api-spec.md` | Vertrag für das Backend, mit Stand je Endpunkt |

## Starten

```bash
cp .env.example .env          # Passwort ändern
docker compose up -d --build
docker compose run --rm api python -m app.seed_geonames   # einmalig, ~15 s
```

http://localhost:8080 — API unter `/api/v1`, interaktive Doku unter
`/api/v1/docs`.

Der Worker holt alle 10 Minuten den jüngsten ICON-D2-Lauf; nach dem ersten
Durchlauf (rund 2 s für 20 Felder) liefert `/api/v1/clouds` Werte.

Tests:

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests
```

## Astronomie

Kontaktzeiten C1–C4, Bedeckungsgrad, Sonnenhöhe und Azimut, Sonnenuntergang
sowie die Isolinien der Bedeckung werden **im Browser** gerechnet — aus den
polynomialen Besselschen Elementen des NASA Five Millennium Canon of Solar
Eclipses (F. Espenak, GSFC), t0 = 2026 Aug 12, 18.000 TDT, ΔT = 75,4 s.

```
x  =  0.4755140 + 0.5189249·t − 0.0000773·t² − 0.0000080·t³
y  =  0.7711830 − 0.2301680·t − 0.0001246·t² + 0.0000038·t³
d  = 14.7966700 − 0.0120650·t − 0.0000030·t²
μ  = 88.747787 + 15.003090·t
tan f1 = 0.0046141   tan f2 = 0.0045911
```

Stichproben (MESZ): Köln Maximum 20:12:44, 88,2 % · Berlin 20:08:19, 84,8 % ·
Freiburg 20:17:11, 90,3 % · München 20:15:43, 88,8 %.

`backend/app/eclipse.py` ist eine Portierung derselben Rechnung — sie wird für
die Wolkenauswertung zur lokalen Maximumszeit gebraucht. Beide Fassungen werden
gegen gemeinsame Stützstellen geprüft (`backend/tests/test_eclipse.py`), die
Referenz erzeugt `node backend/scripts/golden_eclipse.mjs`.

## Die entscheidende Zahl

Die Sonne steht im Maximum sehr tief: **1,8° in München, 3,3° in Berlin,
7,3° auf Sylt**, Azimut durchweg 285–290°.

Daraus folgt fast alles andere. Eine 5 m hohe Hecke in 150 m Entfernung
verdeckt München im Maximum vollständig; eine 20 m Baumreihe verdeckt ganz
Deutschland. Ein 800 m höherer Berg in 40 km Entfernung trägt dagegen nur 1°
bei. Das Nahfeld schlägt das Fernfeld um fast eine Größenordnung — und der
gebrauchte Azimutsektor ist 30° breit, kein Vollkreis.

## Wolken

ICON-D2 vom DWD (Open Data, ohne Anmeldung), 0,02° ≈ 2,2 km, 48 h Vorlauf.
Geholt werden vier Wolkenvariablen zu fünf Zeitpunkten rund um das Ereignis.

Die Trennung nach Schichten ist kein Detail: hohe Zirren (ab 400 hPa) lassen
die Sichel durch, tiefe Bewölkung (unter 800 hPa) beendet die Beobachtung.
Der DWD kodiert alle drei Schichten als denselben GRIB-Parameter 0/6/22 und
unterscheidet sie ausschließlich über die begrenzenden Druckflächen — der
Ingest prüft das bei jeder Datei, weil eine Verwechslung einen plausibel
aussehenden, aber falschen Wert ergäbe.

GRIB2 kommt als *simple packing* (Template 5.0, 16 bit) mit Bitmap. Dafür
reicht `backend/app/grib2.py`; eccodes und GDAL bleiben aus dem Image.

## Standort-Score

```
0,42 · Horizontfreiheit West/NW   (Sonnenhöhe minus Geländekante im Maximum)
0,25 · Wolken                      (Klimatologie, später Prognose)
0,18 · Bedeckungsgrad              (normiert auf 82–91 %)
0,15 · Zugänglichkeit              (frei / eingeschränkt)
```

Noch nicht im Backend — hängt an `/api/v1/horizon`.

## Datenschutz

Genau **ein** Fremdhost: `tile.openstreetmap.org` für die Kartenkacheln.
Alles andere kommt vom eigenen Server — Leaflet, React, Schriften, Ortssuche,
Wolkendaten. Die CSP in `web/Caddyfile` erzwingt das über `connect-src 'self'`,
`font-src 'self'` und ein `img-src`, das genau diesen einen Host zulässt.

Was dabei zu wissen ist:

* **Kachelanfragen verraten den Kartenausschnitt** — also grob den gesuchten
  Ort — plus die IP. Auf einer Seite, deren Kerninteraktion „gib deinen
  Standort ein" ist, ist das die aussagekräftigste Spur. Gehört in die
  Datenschutzerklärung.
* **`Referrer-Policy` ist `strict-origin-when-cross-origin`, nicht
  `no-referrer`.** Die OSM-Kachelpolicy verlangt ausdrücklich einen gültigen
  Referer. Nach außen geht damit nur die Herkunft, nie der Pfad.
* **OSM sichert nichts zu:** „Availability is best-effort: there is no SLA or
  guarantee. We may block access, without notice, if your usage degrades the
  service." Für die bundesweite Lastspitze am 12.8. ist das ein Risiko.
  `frontend/config.js` hält CARTO als Alternative bereit — Umstellen ist eine
  Zeile.
* **`script-src` braucht `'unsafe-inline'` und `'unsafe-eval'`**, weil die
  DC-Laufzeit die Logik-Klasse aus dem `<script type="text/x-dc">`-Block als
  String auswertet. Ein kompilierter Build aus dem DC-Tooling würde beides
  überflüssig machen.

### Vendoring

`frontend/vendor/` enthält Leaflet 1.9.4, React und ReactDOM 18.3.1 (UMD) sowie
die Schriften Caprasimo und Figtree (SIL OFL 1.1, aus dem
Google-Fonts-CSS2-Endpunkt).

React wird **vor** `support.js` geladen. Die DC-Laufzeit steigt in
`loadReactUmd()` bei vorhandenem `window.React` aus und holt dann nichts mehr
von unpkg — damit bleibt `support.js` unverändert und übersteht eine
Neuerzeugung durch das DC-Tooling. Die unpkg-URLs stehen weiter in der Datei,
werden aber nie erreicht. Babel lädt die Laufzeit nur für `x-import` mit JSX,
das die Seite nicht verwendet.

Figtree ist eine Variable Font: eine Datei deckt 400–700 ab. Ein Aufruf mit
`wght@400;500;600;700` liefert dieselbe Datei viermal — `wght@400..700` ist
richtig und spart hier 90 kB.

## Offen

- **Die Wolkenprognose hat noch keinen Platz im Design.** `frontend/api.js`
  liefert sie, aber die vorhandenen Slots auf der Standorte-Seite meinen
  Klimatologie („% klare Sicht im Mittel"), nicht Vorhersage.
- Die Standortbewertung läuft weiter auf den erfundenen Horizontprofilen aus
  `data.js` — hängt an `/api/v1/horizon`
- `/api/v1/elevation` und `/api/v1/horizon` (Copernicus GLO-30, DOM1)
- Wolkenklimatologie CM SAF
- Englische Fassung (Umschalter ist angelegt, Texte fehlen)
- Seiten Beobachtungstipps, Fotografie, FAQ, Impressum

## Quellen

Besselsche Elemente: NASA/GSFC Five Millennium Canon of Solar Eclipses,
Fred Espenak. Wolken: Deutscher Wetterdienst, ICON-D2 (Open Data).
Orte: GeoNames (CC BY 4.0). Karten: OpenStreetMap-Mitwirkende, CARTO.
Design-System: *Organic*.
