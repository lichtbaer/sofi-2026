# Sonnenfinsternis 2026 — Deutschland

Website zur partiellen Sonnenfinsternis am **12. August 2026** in Deutschland.
Kontaktzeiten, Bedeckungsgrade, Isolinien und Standortbewertung.

## Was hier drin ist

| Datei | Inhalt |
| --- | --- |
| `Sonnenfinsternis 2026.dc.html` | Die Seite: Start, Zeiten & Orte, Beste Standorte, Sicherheit |
| `eclipse.js` | Finsternisrechnung — Besselsche Elemente, lokale Umstände, Isolinien |
| `data.js` | Ortsdatenbank und Mock der Backend-Endpunkte |
| `api-spec.md` | Vertrag für das Backend (Geocoding, HORAYZON, Wolken, Ranking) |
| `support.js` | Laufzeit der Design-Komponente |
| `_ds/` | Design-System *Organic* (Tokens, Komponenten) |

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

Isolinien entstehen aus einem 0,2°-Raster über Deutschland (maximale
Obskuration je Gitterpunkt) plus Marching Squares.

## Backend

Existiert noch nicht. `api-spec.md` beschreibt die Endpunkte:

- `GET /api/geocode` — Ortssuche über BKG oder Nominatim
- `GET /api/elevation` — Geländehöhe aus DGM1
- `GET /api/horizon` — **HORAYZON**, DOM1 im Nahfeld (< 2 km), DGM im Fernfeld (bis 200 km)
- `GET /api/clouds` — Wolkenklimatologie (CM SAF) und ICON-D2-Prognose
- `GET /api/sites` — bewertete Standorte im Umkreis
- `POST /api/spots` — eigene Beobachtungsorte speichern und teilen

Solange das Backend fehlt, liefert `data.js` Beispielwerte für Horizontprofile,
Wolkenklimatologie und Zugangshinweise. Der Rest rechnet echt.

## Standort-Score

```
0,42 · Horizontfreiheit West/NW   (Sonnenhöhe minus Geländekante im Maximum)
0,25 · Wolkenklimatologie          (klarer Himmel am 12.8., 18–19 UTC)
0,18 · Bedeckungsgrad              (normiert auf 82–91 %)
0,15 · Zugänglichkeit              (frei / eingeschränkt)
```

## Lokal starten

Die Seite lädt ES-Module, braucht also einen Server — nicht `file://`:

```bash
python3 -m http.server 8000
# http://localhost:8000/Sonnenfinsternis%202026.dc.html
```

Kartenkacheln kommen von CARTO, Leaflet und die Schriften von CDNs.

## Offen

- Englische Fassung (Umschalter ist angelegt, Texte fehlen)
- Seiten Beobachtungstipps, Fotografie, FAQ, Impressum
- Backend inkl. HORAYZON-Pipeline

## Quellen

Besselsche Elemente: NASA/GSFC Five Millennium Canon of Solar Eclipses,
Fred Espenak. Karten: OpenStreetMap-Mitwirkende, CARTO.
Design-System: *Organic*.
