# Oberfläche und Bedienung — Befund und Plan

Stand: 11. August 2026. Grundlage ist die ausgelieferte Seite, nicht der
Quelltext allein: `frontend/` wurde statisch serviert und in Chromium auf
1280×900 und 390×844 vermessen — Screenshots aller sieben Seiten,
Tab-Reihenfolge, Paint-Zeiten, Zustand ohne JavaScript, gerechnete
Kontrastwerte. Was hier steht, ist gemessen oder aus der Datei belegt.

Die API lief dabei nicht. Das ist kein Mangel des Tests, sondern der
interessantere Fall: es zeigt genau die Zustände, die am Ereignisabend unter
Last auftreten — fehlende Wolkenprognose, fehlendes Horizontprofil.

## Was schon trägt

Der Ausgangspunkt ist gut, und das ist der Maßstab für alles Folgende. Die
Bildsprache sitzt: warmer Cremegrund, Terrakotta-Akzent, Caprasimo über
Figtree, großzügige Radien. Die Startseite ist eine ordentliche Seite —
Hero, drei Kennzahlen, drei Einstiege, fertig. Die Fachtexte auf
Beobachtungstipps, Fotografie und Sicherheit sind besser als das, was
vergleichbare Seiten zu diesem Ereignis anbieten.

Vor allem: die Seite ist inhaltlich ehrlich. Kein Score ohne Horizontwert,
„verdeckt" als Aussage und „frei" als Obergrenze, genau ein Fremdhost. Diese
Haltung ist die eigentliche Substanz — der Plan unten will sie nicht
antasten, sondern in der Oberfläche sichtbar machen, wo sie derzeit noch wie
ein Fehler aussieht.

## Befunde

### 1. Die Seite hat keinen Titel

`document.title` ist leer. Es gibt keine `<meta name="description">`, kein
Favicon, kein Open Graph, kein `theme-color`. Gemessen, nicht vermutet.

Die Folgen: der Browser-Tab zeigt die URL, ein Lesezeichen ist namenlos, und
ein in WhatsApp, Signal oder Mastodon geteilter Link erzeugt eine nackte URL
ohne Vorschaubild und ohne Zeile darunter.

Für eine Seite, deren Verbreitung am Vorabend eines bundesweiten Ereignisses
fast vollständig über Weiterleiten läuft, ist das der teuerste Einzelfehler
im ganzen Projekt — und der billigste zu behebende.

### 2. Der abgedunkelte Text liegt unter dem Schwellenwert

Die Seite arbeitet durchgehend mit `rgba(32,30,29,α)` statt mit Farbwerten —
202 Vorkommen. Gerechnet gegen den Cremegrund `#f5ead8` und den Sandgrund
`#ebddc5`:

| Verwendung | Wert | Kontrast | AA (4,5:1) |
| --- | --- | --- | --- |
| Einleitungsabsatz jeder Seite | `0.62` auf Creme | 4,38 | knapp verfehlt |
| Zeilennotizen, Kicker | `0.55` auf Creme | 3,57 | nein |
| Bildunterschrift 11 px | `0.5` auf Creme | 3,10 | nein |
| Kartenhinweis 11 px | `0.5` auf Sand | 2,99 | nein |
| Balkenlabel 9 px | `0.55` auf Sand | 3,45 | nein |
| Fließtextlink `#b2622d` | auf Creme | 3,77 | nein |
| SVG-Achsen `ivory 0.45` | auf Tinte | 3,91 | nein |

Das Muster ist systematisch und geht in die falsche Richtung: je kleiner der
Text, desto schwächer der Kontrast. Der schlechteste Wert der Seite, 2,99,
sitzt auf 11-px-Text.

Der Zusammenhang mit dem Anlass ist nicht akademisch. Diese Seite wird abends
im Freien auf einem Telefon gelesen, bei tief stehender Sonne oder in der
Dämmerung, von Leuten, die gleichzeitig ein Stativ aufbauen. Das ist der
Anwendungsfall, für den die Schwellenwerte gedacht sind.

Die Reparatur steht bereits im Repository. Das Design-System *Organic* liefert
Ramps, deren Stufen genau passen:

- `--color-neutral-700` `#645c50` → **5,53** auf Creme, ersetzt 0.62 / 0.55 / 0.5
- `--color-accent-700` `#8c491a` → **5,72** auf Creme, ersetzt `#b2622d` im Fließtext

Sein `readme.md` sagt das sogar selbst: *„for paragraph-size text in the accent
use a deep ramp step (`--color-accent-700` on this ground) rather than the
accent itself."* Die Vorgabe ist da, sie wird nur nicht befolgt.

### 3. Die Kernfunktion der Standorte-Seite ist per Tastatur nicht erreichbar

Getestete Tab-Reihenfolge auf `#/standorte`: Logo → fünf Navigationslinks →
DE → EN → Radius-Regler → „Ort ändern" → Fußzeile.

Die neun Standortkarten kommen darin nicht vor. Sie sind `<div onClick>`, also
weder fokussierbar noch mit Enter auslösbar, ohne Rolle und ohne Ansage des
ausgewählten Zustands. Wer nicht mit der Maus zeigen kann, kann auf dieser
Seite keinen Standort auswählen. Dasselbe gilt für die Vorschlagsliste der
Ortssuche: `<div onClick>`, keine `combobox`/`listbox`-Semantik, keine
Pfeiltastenbedienung.

Dazu im selben Feld:

- **Fokus** ist überall der Browser-Standard (`outline: 1px auto`). Auf den
  dunklen Karten und im dunklen Hero ist er praktisch unsichtbar. Das
  Design-System verlangt ausdrücklich `:focus-visible { outline: 2px solid
  var(--color-accent); outline-offset: 2px }` — im ganzen Dokument steht kein
  einziges `:focus`.
- **Suchfeld ohne Label**, nur Placeholder. Verschwindet beim Tippen.
- **Menü-Button** ohne `aria-expanded`, ohne `aria-controls`; Escape schließt
  das Menü nicht (getestet: Linkzahl bleibt nach Escape unverändert).
- **5 von 7 SVG ohne Textalternative** — darunter die Sichel und das
  Horizontprofil, also die beiden Grafiken, die die Kernaussage tragen.
- **Überschriftensprung** h1 → h3 auf „Zeiten & Orte", kein h2.
- **`prefers-reduced-motion`** wird nirgends abgefragt; der pulsierende Punkt
  im Hero läuft unbedingt.

### 4. Screenreader hören jedes Label zweimal, in zwei Sprachen

Die Zweisprachigkeit ist als Doppelmarkup gelöst: beide Fassungen stehen im
DOM, eine wird per `html[lang] [data-l]` ausgeblendet. `display: none` nimmt
den Text zwar aus der Vorlesereihenfolge — aber die Konstruktion schlägt an
zwei Stellen durch, an denen kein CSS greift:

Der ausgelesene Seiteninhalt lautet „Zeiten & OrteTimes & Places",
„StandorteLocations", „Die tief stehende FinsternisThe low-standing eclipse".
So landet er in jedem Kontext, der CSS nicht auswertet — Textextraktion,
Vorschaugeneratoren, Suchmaschinen-Snippets, Übersetzungsdienste.

### 5. Der erste Frame zeigt beide Sprachen ineinander

`<html>` trägt kein `lang`-Attribut. Die Ausblendregel greift erst, wenn
JavaScript es setzt. Bis dahin — und dauerhaft, wenn JavaScript ausfällt —
steht auf dem Bildschirm:

- alle Texte in beiden Sprachen hintereinander
- das Mobilmenü aufgeklappt, auch auf dem Desktop
- unaufgelöste `{{ Platzhalter }}` in den Diagrammen

Lokal gemessen: First Contentful Paint 256 ms, danach räumt die DC-Laufzeit
auf. Über Mobilfunk am Ereignisabend ist dieses Fenster deutlich länger.

Die Reparatur ist ein Attribut: `<html lang="de">`. Das trifft zwar die
Vorauswahl für englischsprachige Besucher nicht mehr im ersten Frame, aber
ein kurz falsch beschrifteter Zustand ist besser als ein doppelt
beschrifteter.

### 6. Auf dem Handy passiert beim Antippen einer Standortkarte nichts

Auf 390 px steht das Detailpanel unter der vollständigen Neunerliste — rund
2000 px weiter unten. Wer eine Karte antippt, sieht keine Reaktion; die
Auswahl wirkt außerhalb des Sichtfelds. Das `position: sticky; top: 80px` der
Detailspalte läuft im Einspaltenfluss ins Leere.

Ebenfalls mobil:

- **Die Diagramme sind unlesbar.** Beide SVG haben eine feste viewBox
  (620×210 und 600×230) und skalieren auf rund 290 px Breite. Die als 11 px
  ausgezeichneten Achsenbeschriftungen landen bei etwa 5 px. Text in SVG
  skaliert mit — das ist der eine Fall, in dem eine px-Angabe kein px bleibt.
- Die Kartenlegende bricht in zwei ungleiche Zeilen um.
- Die Kontaktzeiten — der meistgesuchte Inhalt der Seite — stehen erst nach
  Karte, Ortskarte und Wolkenblock, gut anderthalb Bildschirmhöhen unten.

### 7. Auf dem Desktop kippt „Zeiten & Orte" aus der Balance

Die linke Spalte endet bei etwa 830 px Höhe, die rechte läuft bis 1320 px.
Darunter steht eine große leere Fläche. Die Karte ist auf
`min(58vh, 460px)` gedeckelt, obwohl sie die Kerninteraktion der Seite ist,
während das Verlaufsdiagramm sich in die schmale rechte Spalte klemmt, wo
seine Zeitachse am wenigsten Platz hat.

### 8. Fehlende Daten sehen aus wie kaputte Software

Ohne Horizontdienst zeigt jede der neun Standortkarten einen Gedankenstrich
über dem Wort „SCORE" und einen leeren Balken über „HORIZONT". Inhaltlich ist
das genau richtig und im README begründet: der Horizont wiegt 0,42, und die
übrigen Faktoren umzugewichten ergäbe eine Zahl, die wie eine Bewertung
aussieht und die entscheidende Größe nicht kennt.

Nur sagt die Oberfläche das nicht. Neun Karten mit neun Strichen lesen sich
als Ausfall, nicht als Zurückhaltung. Die inhaltlich stärkste Entscheidung des
Projekts erscheint als Bug.

Verschärft wird das im Detailpanel: das Horizontdiagramm zeichnet Achsen,
Gitternetz, Augenhöhenlinie und Sonnenbahn — vollständig, als läge ein Profil
vor —, und darunter steht „Kein Horizontprofil verfügbar". Ein Diagramm, das
seinem eigenen Begleittext widerspricht.

Dasselbe Muster ohne Wolkendaten: „Prognose nicht erreichbar" erscheint als
Karte in derselben Gestaltung wie Inhaltskarten, direkt unter dem
Ortsnamen — an der prominentesten Stelle der Seite.

Ladeskelette gibt es nirgends; die Blöcke erscheinen hart.

### 9. Die Karte folgt der Auswahl nicht

In der gesamten Datei steht kein `setView`, `flyTo`, `panTo` oder
`fitBounds`. Nach einer Ortssuche oder einem Klick auf „Mein Standort" wandert
der Marker, die Ansicht bleibt auf Zoom 5 über Gesamtdeutschland stehen. Wer
Kassel sucht, muss den Marker selbst finden.

Dazu: der Kartenklick schreibt fest verdrahtet `'Gewählter Punkt'` in den
Zustand — auch im englischen Modus. `scrollWheelZoom` ist ausgeschaltet
(richtig), aber ohne Hinweis, wie stattdessen gezoomt wird. Der
Kartencontainer hat weder Rolle noch Beschriftung.

### 10. Der Countdown kennt nur „davor"

Nach dem Maximum friert der Zähler auf `0 / 00 / 00 / 00` ein, und darunter
steht weiterhin „bis zum Maximum in Frankfurt am Main". Es gibt keinen
Zustand für „läuft gerade" und keinen für „vorbei".

Ab morgen 20:13 MESZ ist das der Dauerzustand der Startseite — also genau in
den Stunden, in denen die Seite am meisten aufgerufen wird. Während des
Ereignisses selbst wäre ein Live-Zustand („C1 überschritten, Maximum in 23
Minuten") der wertvollste Inhalt, den die Startseite anbieten kann.

### 11. Dieselben Ziele heißen an drei Stellen verschieden

| Ziel | Kopfzeile | Mobilmenü | Fußzeile |
| --- | --- | --- | --- |
| `#/tipps` | Beobachten | Beobachtungstipps | Beobachtungstipps |
| `#/standorte` | Standorte | Beste Standorte | Beste Standorte |
| `#/start` | nur Logo | Start | — |
| `#/faq` | — | FAQ | FAQ |

FAQ fehlt in der Kopfzeile ganz, obwohl die Seite gepflegt und gut ist.

### 12. Das Design-System liegt ungenutzt im Repository

Zahlen aus `Sofi.dc.html`: **463** `style="…"`-Attribute, **150**
Hex-Literale, **202** `rgba(32,30,29,α)`-Angaben, **12** verschiedene
`font-size`-Werte zwischen 9 px und 15 px allein im Kleintextbereich.

Daneben liegt `frontend/_ds/organic-…/` vollständig: Tokensheet, drei
OKLCH-Ramps, Komponentenklassen für Buttons, Felder, Karten, Tabellen, Navigation
und Dialoge, dazu ein Adherence-Linter. Die Seite bindet nichts davon ein.
Sein `readme.md` beginnt mit: *„Never hard-code a hex, a font name or a px
value the tokens already carry."*

Deshalb ist jeder Kontrastfehler oben 30- bis 200-fach zu reparieren statt
einmal.

**Fallstrick beim Einbinden:** `_ds/…/styles.css` importiert in Zeile 2
`fonts.googleapis.com`. Das bricht die CSP (`font-src 'self'`) und das
Versprechen „genau ein Fremdhost" aus README und Datenschutzerklärung. Die
Zeile muss beim Übernehmen raus — Caprasimo und Figtree liegen bereits unter
`vendor/fonts/`.

## Plan

Drei Stufen, nach Wirkung je Aufwand sortiert. Stufe 0 ist so geschnitten,
dass sie heute fertig wird und morgen früh ausgeliefert werden kann.

### Stufe 0 — vor dem Ereignis (etwa ein halber Tag, geringes Risiko)

Nur Änderungen ohne Umbau: Attribute, Farbwerte, ein zusätzlicher
`<style>`-Block, drei kleine Eingriffe in die Logik.

1. **Kopfdaten.** `<html lang="de">`, `<title>`, Meta-Description, Favicon
   (die Sichel aus dem Logo als SVG), `theme-color`, Open Graph und Twitter
   Card mit Vorschaubild. Behebt Befund 1 und die Hälfte von 5.
   → *größte Wirkung im ganzen Plan, etwa eine Stunde Arbeit*
2. **Kontraststufen ersetzen.** `0.62` / `0.55` / `0.5` → `#645c50`,
   Fließtextlinks und Kickerfarbe → `#8c491a`, SVG-Achsen von `ivory 0.45`
   auf `0.62` anheben, die 9-px-Balkenlabels auf 10 px. Suchen und Ersetzen,
   kein Layoutrisiko. Behebt Befund 2.
3. **Ein `<style>`-Block im `<helmet>`** mit dem, was inline nicht geht:
   `:focus-visible`-Ring nach Systemvorgabe, `@media (prefers-reduced-motion)`
   für den Pulspunkt, `:hover`/`:active` für Karten und Buttons.
4. **Standortkarten und Suchvorschläge bedienbar machen.** `<div onClick>` →
   `<button>` beziehungsweise Listbox mit Pfeiltasten, `aria-current` für die
   ausgewählte Karte. Behebt den Kern von Befund 3.
5. **Karte folgt der Auswahl.** `setView` mit passendem Zoom nach Suche, nach
   „Mein Standort" und nach Kartenklick; `'Gewählter Punkt'` übersetzen.
   Behebt Befund 9.
6. **Countdown-Zustände.** „läuft gerade" mit Restzeit bis zum Maximum,
   danach „vorbei" mit Verweis auf den 2. August 2027. Behebt Befund 10.
7. **Mobiles Detailpanel.** Bei Auswahl an den Anfang der Liste rücken oder
   dorthin scrollen, damit Antippen sichtbar wirkt. Behebt Befund 6, erster
   Teil.
8. **Menü-Button:** `aria-expanded`, `aria-controls`, Escape schließt.

### Stufe 1 — Substanz (zwei bis drei Tage)

9. **Styles aus dem Markup ziehen.** Eine verlinkte CSS-Datei mit den
   *Organic*-Tokens und einer schmalen Klassenschicht (`.card`, `.stat`,
   `.row`, `.chip`, `.bar`, `.panel`), das Markup behält seine Struktur. Der
   Google-Fonts-Import bleibt draußen. Ab hier ist jede Farb- und
   Abstandsfrage an einer Stelle zu beantworten. Grundlage für alles Weitere;
   behebt Befund 12.
10. **Diagramme responsiv.** Beschriftungen aus dem SVG-Koordinatensystem
    lösen (`vector-effect` beziehungsweise HTML-Overlay), auf schmalen
    Breiten weniger Achsenmarken, Mindestschriftgröße 11 px am Gerät. Behebt
    Befund 6, zweiter Teil.
11. **Leerzustände, die die Haltung zeigen.** Statt „—" über „SCORE" ein
    ruhiger Hinweis auf der Karte („Horizont fehlt — ohne ihn keine
    Bewertung"), das Horizontdiagramm bei fehlendem Profil gar nicht erst
    zeichnen, sondern eine erklärte Leerfläche zeigen. Ladeskelette in
    Kartenform. Behebt Befund 8.
12. **„Zeiten & Orte" neu ausbalancieren.** Karte größer und auf Desktop
    sticky, Kontaktzeiten auf dem Handy vor die Karte, Verlaufsdiagramm über
    die volle Breite unter beide Spalten. Behebt Befund 7.
13. **Navigation vereinheitlichen**, FAQ in die Kopfzeile. Behebt Befund 11.
14. **Grafiken beschriften.** Sichel, Horizontprofil und Verlaufskurve
    bekommen `<title>`/`<desc>` und eine Textfassung der Kernaussage.
    Überschriftenebenen korrigieren. Rest von Befund 3.

### Stufe 2 — Ausbau (danach)

15. **Dunkelmodus.** Kein Effekt, sondern Funktion: die Seite wird abends im
    Freien benutzt, und ein cremeweißer Vollbildschirm zerstört die
    Dunkeladaption, die man für eine 2°-Sichel braucht. Automatisch ab
    Sonnenuntergang oder per `prefers-color-scheme`, plus Umschalter.
16. **Zweisprachigkeit richtig lösen.** Das `data-l`-Doppelmarkup durch ein
    Wörterbuch ersetzen — es halbiert das Dokument, behebt Befund 4 und macht
    die englische Fassung überhaupt erst pflegbar (im README als offener
    Punkt geführt).
17. **Die Wolkenprognose bekommt ihren Platz** auf der Standorte-Seite. Die
    dortigen Slots meinen bislang Klimatologie, nicht Vorhersage — steht so
    im README unter „Offen".
18. **Adherence-Linter** aus dem Design-System in die Prüfung aufnehmen,
    damit die Werte nicht wieder auseinanderlaufen.

## Offene Entscheidungen

Vier Weggabelungen, die den Zuschnitt ändern. Bis zur Antwort arbeite ich
nach der jeweils erstgenannten Annahme.

1. **Geht die Seite morgen für dieses Ereignis live?**
   *Annahme: ja.* Deshalb ist Stufe 0 so geschnitten, dass sie ohne
   Strukturumbau auskommt und einzeln ausgeliefert werden kann. Falls das
   Datum für diese Arbeit nicht bindend ist, würde ich stattdessen mit
   Stufe 1 Punkt 9 beginnen — die Tokenschicht zuerst, dann alles andere
   darauf.

2. **Wie frei darf `Sofi.dc.html` umgebaut werden?**
   Das README beschreibt die Datei als vom DC-Tooling verwaltet und begründet,
   warum `support.js` unangetastet bleibt.
   *Annahme: Struktur bleibt, Styles wandern in eine verlinkte CSS-Datei.*
   Das überlebt eine Neuerzeugung am ehesten. Wenn das Tooling ohnehin aus
   dem Spiel ist, wäre der Umbau deutlich gründlicher möglich — vor allem
   Punkt 16.

3. **Wie weit soll sich die Optik verändern?**
   *Annahme: verfeinern, Bildsprache bleibt.* Die Gestaltung ist gut; die
   Probleme liegen in Kontrast, Zuständen und Bedienbarkeit, nicht im
   Entwurf. Ein sichtbarer Umbau — neue Hero-Grafik, andere Kartenästhetik —
   wäre eine eigene Entscheidung und steht nicht in diesem Plan.

4. **Dunkelmodus: Ausbau oder Stufe 0?**
   Ich habe ihn nach Stufe 2 gelegt, weil er ohne die Tokenschicht aus
   Punkt 9 auf 463 Inline-Styles trifft. Wenn er fürs Ereignis wichtiger ist
   als der Rest von Stufe 1, lässt er sich vorziehen — dann aber mit Punkt 9
   zusammen, nicht davor.

## Anhang: Prüfaufbau

```bash
cd frontend && python3 -m http.server 8099
# Chromium aus /opt/pw-browsers, playwright-core, Viewports 1280×900 und 390×844
```

Gemessen wurden: Screenshots aller sieben Seiten in beiden Viewports,
Tab-Reihenfolge über 14 Stationen, `document.title` und Kopfdaten,
Rendering ohne JavaScript, Paint-Zeiten (FCP 256 ms, 27 Anfragen, 445 kB),
Verhalten des Mobilmenüs bei Escape, sowie Kontrastverhältnisse nach
WCAG-2-Formel für 15 Farbpaare der Seite.
