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
| `frontend/data.js` | Ersatzdaten: 54 Städte als Rückfall, Standortliste |
| `frontend/vendor/` | Leaflet, React, Schriften — selbst ausgeliefert |
| `frontend/_ds/` | Design-System *Organic* (Tokens, Komponenten) |
| `backend/` | FastAPI: Ortssuche, Wolkenprognose, lokale Umstände, Horizont |
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

### Produktion: HTTPS mit Let's Encrypt

In der `.env` die Domain und die Standardports setzen:

```bash
SOFI_DOMAIN=horizontfrei.de
WEB_PORT=80
WEB_TLS_PORT=443
```

Caddy holt und erneuert die Zertifikate dann selbst (Ablage im Volume
`caddydata`, überlebt Neustarts), leitet HTTP auf HTTPS um und setzt HSTS.
Voraussetzung: Die DNS-Einträge der Domain zeigen auf den Server, Port 80
und 443 sind von außen erreichbar. Mehrere Hostnamen gehen durch Leerzeichen
getrennt (`SOFI_DOMAIN="horizontfrei.de www.horizontfrei.de"`). Ohne
`SOFI_DOMAIN` bleibt alles beim unverschlüsselten HTTP auf `WEB_PORT` —
für die lokale Entwicklung.

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

## Horizont

`/api/v1/horizon` rechnet aus **Copernicus DEM GLO-30** (ESA, offen, ohne
Anmeldung): ein Strahl je 0,25° Azimut über 240°–330°, bis 40 km hinaus, mit
Erdkrümmung und Refraktion (k = 0,13). Eine Punktabfrage on demand statt einer
vorberechneten Spalte — deshalb funktioniert auch der Klick auf eine beliebige
Stelle der Karte.

Was ein Aufruf kostet, steht hier bewusst nicht. Ein Aufruf tastet 361 Azimute
mal 477 Distanzen ab, also 172 197 Zellen eines Memmaps von knapp 3 GB. Das ist
kein CPU-Maß, sondern eines für den Seitencache: kalt und warm liegen
Größenordnungen auseinander, und unter Parallellast konkurrieren die Abfragen
um denselben Cache. Wer die Zahl braucht — für eine Vorberechnung etwa — misst
sie auf der Zielmaschine, kalt und warm getrennt.

### Was GLO-30 zeigt und was nicht

Es ist ein *Oberflächenmodell* und enthält Bewuchs. **Auf Gebäude ist dennoch
kein Verlass.** Nachgemessen an der Kachel N50/E008, Frankfurter Bankenviertel,
1,2-km-Feld:

| | |
| --- | --- |
| Median | 106 m |
| höchster Wert | 127 m |
| Dach des Commerzbank-Turms | ~360 m über NN |

Ein 259-m-Hochhaus ist nicht in den Daten. Die Georeferenzierung der Messung
ist gegengeprüft: Großer Feldberg 871 m, Kachelmaximum 885 m am Gipfel.

Warum, lässt sich aus einer Kachel nicht belegen. Naheliegend ist nicht
„herausgerechnet", sondern „nie gemessen": TanDEM-X ist ein interferometrisches
Radar, dichte Hochhausbebauung erzeugt Layover und Radarschatten, die Zellen
werden zu Datenlücken, und deren Füllung interpoliert aus der Umgebung. Für
flache Bebauung ist **ungeprüft**, was ankommt — ein Schnitt über ein Dorf in
der Wetterau war nicht auswertbar, weil dort 32 m Geländeanstieg auf 3 km
jeden Objektbeitrag überdecken.

Dazu kommt die Flächenmittelung, und die ist reine Arithmetik:

| Objekt | Anhebung seiner 30-m-Zelle |
| --- | --- |
| Hecke 5 m hoch, 3 m breit | 0,5 m |
| Hecke 5 m hoch, 10 m breit | 1,7 m |
| Baumreihe 20 m hoch, 10 m breit | 6,7 m |

Das Signal wird gedämpft, der Höhenfehler des Rasters nicht. Ein Höhenfehler
von 2 m entspricht in 90 m Entfernung bereits 1,27° — mehr als die gesamte
Sonnenhöhe in München. Deshalb holt auch ein kleinerer Mindestabstand als die
90 m aus `horizon_min_distance_m` die Information nicht zurück: **sie steckt
nicht in den Daten.** Das Nahfeld unter etwa 600 m braucht eine andere Quelle,
keine andere Schwelle.

Damit ist der Fehler einseitig, und die Oberfläche muss ihn einseitig
darstellen: **„verdeckt" ist eine Aussage, „frei" ist eine Obergrenze.** Wer
mehr Daten hinzufügt, kann den Horizont nur anheben. Jede Näherung im Backend
ist entsprechend gewählt — Standhöhe aus dem Zellwert statt aus dem
Umfeldminimum, damit ein Gipfel nicht in die Hangschulter rutscht und ein
falsches „verdeckt" erzeugt.

Ein DOM1 der Länder wäre im Nahfeld deutlich besser. Es liegt aber in sechzehn
Formaten unter sechzehn Lizenzen vor, und der Aufwand dafür ist Integration,
nicht Volumen — er schrumpft nicht, wenn man weniger Fläche braucht.

Der Worker holt die rund 3 GB Kacheln beim Start, wenn sie fehlen, und
verrechnet sie zu einem 2,85-GB-Mosaik auf dem Volume (int16, Dezimeter,
memmap). Bis das steht, antwortet `/horizon` mit `503` und `/health` meldet
`terrain: false`.

## Standort-Score

```
0,42 · Horizontfreiheit West/NW   (Sonnenhöhe minus Geländekante im Maximum)
0,25 · Wolken                      (Klimatologie, später Prognose)
0,18 · Bedeckungsgrad              (normiert auf 82–91 %)
0,15 · Zugänglichkeit              (frei / eingeschränkt)
```

Ohne Horizontwert gibt es keinen Score: er wiegt 0,42, und die übrigen drei
umzugewichten ergäbe eine Zahl, die wie eine Bewertung aussieht und die
entscheidende Größe nicht kennt. Fehlt er, steht dort ein Strich.

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
- Wolkenklimatologie CM SAF
- Die Koordinaten in `SITES` zeigen teils neben den Gipfel: Hesselberg liest
  596 m statt 689 m, Kalmit 532 m statt 673 m. Mit dem Höhenmodell fällt das
  jetzt auf — vorher hat das Mock-Profil jede Koordinate durchgewunken.
- Nahfeld unter 30 m Rasterweite (einzelne Hecken, Gebäude). Kandidaten wären
  OSM-Gebäudeumrisse und eine 10-m-Kronenhöhenkarte — beide bundesweit aus je
  einer Quelle, anders als DOM1.
- Englische Fassung (Umschalter ist angelegt, Texte fehlen)
- Seiten Beobachtungstipps, Fotografie, FAQ, Impressum

## Quellen

Besselsche Elemente: NASA/GSFC Five Millennium Canon of Solar Eclipses,
Fred Espenak. Wolken: Deutscher Wetterdienst, ICON-D2 (Open Data).
Höhenmodell: Copernicus DEM GLO-30, ESA / Copernicus Programme.
Orte: GeoNames (CC BY 4.0). Karten: OpenStreetMap-Mitwirkende, CARTO.
Design-System: *Organic*.
