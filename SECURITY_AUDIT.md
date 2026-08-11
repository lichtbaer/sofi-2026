# Sicherheits- und Datenschutz-Audit — SoFi 2026

**Stand:** 11. August 2026 (ein Tag vor dem Ereignis) ·
**Geprüfter Stand:** `cbe0e55` ·
**Umfang:** Backend (FastAPI), Frontend (DC/React), Caddy, Docker-Compose, PostGIS-Schema, Datenpipelines (ICON-D2, GeoNames)

---

## 1. Zusammenfassung

Die Codebasis ist für ihr Alter ungewöhnlich sauber: durchgängig parametrisiertes SQL,
keine Cookies, kein Tracking, alle Fremdbibliotheken selbst ausgeliefert, ein bewusst
strikter GRIB2-Parser, Container ohne Root, Datenbank ohne Host-Port. Die
Datenschutz-Architektur („genau ein Fremdhost") ist als Designentscheidung erkennbar
und im README ehrlich dokumentiert.

Die kritischen Lücken liegen nicht im Code, sondern **im Betrieb und im Rechtlichen**:

| Prio | Befund | Kategorie |
| --- | --- | --- |
| **K1** | Kein TLS im Stack — Standortsuchen laufen im Klartext — *umgesetzt 11.8.* | OWASP A02 |
| **K2** | Impressum und Datenschutzerklärung fehlen | DSGVO Art. 13 / DDG §5 |
| **H1** | Access-Logs protokollieren IP + Suchbegriffe + Koordinaten | DSGVO / A09 |
| **H2** | Kein Rate-Limiting, keine Lastabwehr — am Ereignistag riskant | A04 |
| **H3** | LIKE-Wildcards in der Ortssuche nicht escaped — *behoben 11.8.* | A03 (Injection-Klasse) |
| **H4** | Default-Datenbankpasswort `sofi` als Fallback in docker-compose — *behoben 11.8.* | A05 |

**Umsetzungsstand:** H3, H4, M3, M6 und M7 sind behoben (inkl.
Regressionstests in `backend/tests/test_api_validation.py`); K1 ist
umgesetzt — Let's Encrypt über `SOFI_DOMAIN`, wirksam sobald das Deployment
die Domain und die Ports 80/443 setzt. Offen bleiben K2, H1, H2 sowie die
übrigen M-/N-Befunde.

Kein Befund erlaubt Remote Code Execution, Datendiebstahl oder Kontenübernahme —
die API ist lesend, hält keine Nutzerdaten und kennt keine Accounts. Die realen
Risiken sind **Verfügbarkeit am 12.8.** und **Datenschutz-Compliance**.

---

## 2. Positivbefunde (beibehalten)

* **SQL-Injection:** Alle Queries laufen über psycopg-Parameter (`%(key)s`, `%s`).
  Die einzigen f-Strings in SQL (`ANALYZE {table}` in `seed_geonames.py:235`)
  verwenden hartkodierte Konstanten. ✔
* **Eingabevalidierung:** Pydantic/FastAPI begrenzen `lat`/`lon` (±90/±180), `q`
  (1–80 Zeichen), `limit` (1–25), `variable` (Regex-Whitelist), `elevation`
  (−500…5000). ✔
* **Kein CSRF-Angriffsvektor:** GET-only-API, keine Cookies, keine Sessions. ✔
* **XSS:** Die DC-Laufzeit rendert Templates über React-Elemente — Interpolationen
  werden escaped. Nutzereingaben (Suchbegriff, Ortsnamen aus der DB) landen nie in
  `innerHTML`. Leaflet-Tooltips enthalten nur numerische Werte. ✔
* **SSRF:** Keine nutzergesteuerten URLs; Ingest-Ziele kommen ausschließlich aus
  der Konfiguration. ✔
* **Deserialisierung:** `np.load` ohne `allow_pickle` (Default `False`) — keine
  Pickle-Ausführung über die Felddateien. ✔
* **Container:** API/Worker laufen als User `sofi` (uid 10001), DB-Init-Skripte
  und Frontend sind read-only gemountet, Postgres hat keinen Host-Port,
  Caddy-Admin-API ist aus (`admin off`), `-Server`-Header entfernt. ✔
* **Secrets:** `.env` ist in `.gitignore`, im Repo liegt nur `.env.example`.
  Keine Schlüssel oder Tokens im Code (es gibt schlicht keine). ✔
* **GRIB2-Ingest:** Signaturprüfung (Disziplin/Kategorie/Nummer + Druckflächen)
  gegen Dateiverwechslung, Gitter-Konsistenzprüfung, strikte Fehler statt stiller
  Falschdaten. Vorbildlich gegen Datenintegritätsfehler (A08). ✔
* **Frontend-Autonomie:** Rechnung im Browser, Fallback auf lokale Städteliste —
  ein totes Backend nimmt die Seite nicht mit. ✔

---

## 3. Befunde

Prioritäten: **K** = kritisch (vor Produktivgang), **H** = hoch (vor dem 12.8.),
**M** = mittel (zeitnah), **N** = niedrig (Gelegenheit).

### K1 — Kein TLS, kein HSTS (OWASP A02: Cryptographic Failures)

`web/Caddyfile:3` schaltet `auto_https off` und lauscht nur auf `:80`. Im Repo
existiert keine TLS-Terminierung. Wird der Stack so betrieben, gehen **alle
Ortssuchen und Koordinaten im Klartext** über die Leitung — auf einer Seite, deren
Kerninteraktion „gib deinen Standort ein" ist, ist das der größte einzelne
Datenschutzmangel. Zusätzlich fehlt `Strict-Transport-Security`.

**Empfehlung (Aufwand: klein):**
* Entweder Caddy selbst terminieren lassen (`auto_https` an, Domain eintragen —
  Caddy holt Zertifikate automatisch) oder dokumentieren, dass ein vorgelagerter
  Proxy TLS macht, und das im Repo festhalten.
* Nach TLS-Aktivierung: `Strict-Transport-Security "max-age=31536000"` und
  `upgrade-insecure-requests` in der CSP ergänzen.

> **Status: umgesetzt (11.08.2026).** Caddy terminiert TLS jetzt selbst:
> `SOFI_DOMAIN` (z. B. `horizontfrei.de`, konfigurierbar über `.env`)
> aktiviert automatische Let's-Encrypt-Zertifikate samt HTTP→HTTPS-Umleitung;
> HSTS (max-age ein Jahr) wird gesetzt. Ohne Domain bleibt die lokale
> Entwicklung bei HTTP. Auf `upgrade-insecure-requests` wurde bewusst
> verzichtet: alle Verweise sind relativ, die Kacheln https — Mixed Content
> kann nicht entstehen, und im HTTP-Entwicklungsbetrieb bräche die Direktive
> die eigenen Assets. **Produktiv wirksam erst, wenn das Deployment
> `SOFI_DOMAIN`, `WEB_PORT=80` und `WEB_TLS_PORT=443` setzt und DNS auf den
> Server zeigt.**

### K2 — Impressum und Datenschutzerklärung fehlen (DSGVO Art. 13, DDG §5)

Die Seiten `impressum` und `faq` sind in `PAGES` angelegt, die Texte fehlen
(README „Offen"). Für eine öffentlich betriebene deutsche Website mit erwarteter
bundesweiter Reichweite ist das Impressum **gesetzlich verpflichtend**; die
Datenschutzerklärung muss mindestens erklären:

* Server-Logs (IP-Adressen, Rechtsgrundlage Art. 6 (1) f, Speicherdauer),
* die Kachelabrufe an `tile.openstreetmap.org` (Drittland-/Drittanbieterhinweis:
  IP + Kartenausschnitt gehen an die OpenStreetMap Foundation, UK),
* `localStorage` für die Sprachwahl (funktional, kein Consent nötig — aber
  erwähnenswert),
* dass Suchbegriffe/Koordinaten nur an den eigenen Server gehen.

**Empfehlung (Aufwand: klein, aber Fachtext):** Texte vor Veröffentlichung
einspielen. Ohne Impressum drohen Abmahnungen — ausgerechnet am reichweitenstärksten
Tag.

### H1 — Access-Logs enthalten personenbezogene Standortdaten (DSGVO, OWASP A09)

Zwei Stellen protokollieren derzeit mehr, als die Datenschutzerklärung je decken
sollte:

1. `web/Caddyfile:50` aktiviert das Access-Log auf stderr — Caddy loggt dabei
   Client-IP **und vollständige URI**, also `?q=<Suchbegriff>` und
   `?lat=…&lon=…`. Damit entsteht serverseitig genau das Bewegungs-/
   Interessensprofil, das die Architektur clientseitig vermeidet.
2. Uvicorn (API-Container) loggt Requests ebenfalls mit Query-String.

Beides landet unrotiert im Docker-Log-Treiber (Standard `json-file`, unbegrenzt).

**Empfehlung (Aufwand: klein):**
* Caddy: Query-Strings aus dem Log entfernen (`log { format filter { request>uri query … } }`)
  oder das Access-Log deaktivieren und nur Fehler loggen; alternativ IPs kürzen.
* Uvicorn: `--no-access-log` in `backend/Dockerfile:22` (Caddy loggt bereits, doppelt
  braucht es niemand — und der API-Log ist der mit den Koordinaten).
* Log-Rotation im Compose (`logging: options: max-size/max-file`) — begrenzt auch
  das Disk-Fill-Risiko.
* Speicherdauer festlegen und in die Datenschutzerklärung aufnehmen.

### H2 — Kein Rate-Limiting, keine Lastabwehr (OWASP A04: Insecure Design)

Kein Layer begrenzt Anfragen: Caddy proxyt alles durch, FastAPI hat kein Limit.
Drei Endpunkte sind teuer:

* `/geocode` — LIKE-Scan über ~80 000 Aliase plus `ST_DWithin`-Subquery pro
  Treffer, bei jedem Tastendruck jedes Besuchers;
* `/clouds/overlay.png` — dekodiert, schneidet und PNG-komprimiert bei **jedem**
  Aufruf neu (`optimize=True`), mit frei wählbarer `bbox` → jede Anfrage ist ein
  Cache-Miss;
* `/circumstances` — reine CPU, unkritisch einzeln, aber unlimitiert.

Am 12.8. abends ist mit der Jahresspitze zu rechnen; ein einzelner aggressiver
Client (oder ein gut gemeintes Embedding der Overlay-URL in einem Forum) genügt,
um die API zu sättigen. Gleichzeitig verstärkt H3 die Kosten pro Request.

**Empfehlung (Aufwand: mittel):**
* Rate-Limit am Caddy (Plugin `caddy-ratelimit`) oder — ohne Custom-Build —
  `slowapi`/eigene Semaphore in FastAPI: z. B. 10 req/s je IP für `/geocode`,
  2 req/s für `overlay.png`.
* Overlay-Rendering cachen: Ergebnis je `(variable, valid_at, bbox)` memoisieren
  (die Vorgabe-BBox deckt praktisch alle legitimen Anfragen ab) oder die
  Standard-PNGs beim Ingest vorrendern; zusätzlich `bbox` auf das Modellgebiet
  begrenzen und exotische Boxen ablehnen.
* `ETag`/`Last-Modified` auf `overlay.png` (der Lauf ändert sich alle 3 h —
  Conditional Requests sparen fast alles).

### H3 — LIKE-Wildcards in der Ortssuche nicht escaped (OWASP A03)

`normalize.search_keys()` lässt `%` und `_` durch (verifiziert:
`search_keys('%') == ('%', '%')`), und `geocode.py:39` baut daraus
`LIKE q.key || '%'`. Ein Request `/api/v1/geocode?q=%` erzeugt das Muster `%%`
— ein Match auf **alle** Aliase: Vollscan über `place_alias`, `GROUP BY` über
alle `place_id`s, Join, Sortierung und je Treffer die PLZ-Nachbarschaftssuche.
`_` wirkt als Ein-Zeichen-Wildcard und liefert zusätzlich falsche Treffer.

Das ist keine Datenabfluss-Lücke (die Daten sind öffentlich), aber ein
**erzwingbarer Worst-Case pro Request** — der perfekte Verstärker für H2 — und ein
Korrektheitsfehler (Suche nach Orten mit Sonderzeichen).

**Empfehlung (Aufwand: sehr klein):** In `geocode.search()` vor dem Query escapen:

```python
def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
```

(auf `key` und `alt` anwenden; `LIKE`-Default-Escape `\` genügt). Alternativ in
`search_keys` alles außer `[a-z0-9 .-]` verwerfen — das passt auch fachlich zu
Ortsnamen und PLZs.

> **Status: behoben (11.08.2026).** `_like_prefix()` in `geocode.py` escaped
> `%`, `_` und `\`; die Muster gehen als eigene Parameter (`key_like`,
> `alt_like`) ins SQL, die Exakt-Treffer-Wertung vergleicht weiter gegen die
> rohen Schlüssel. Tests: `test_api_validation.py`.

### H4 — Default-Datenbankpasswort als Fallback (OWASP A05)

`docker-compose.yml:9/23` fällt ohne `.env` auf `POSTGRES_PASSWORD=sofi` zurück.
Die DB ist zwar nicht am Host exponiert, aber ein vergessenes `.env` fällt so nie
auf — der Stack startet einfach mit `sofi:sofi`. Kombiniert mit einem künftigen
Fehler (Port-Mapping, zusätzlicher Container, Netzwerk-Freigabe) wird daraus ein
echtes Problem.

**Empfehlung (Aufwand: eine Zeile):** Fail-hard statt Fallback:

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD in .env setzen}
```

(gleiches Muster in der `SOFI_DATABASE_URL`). `POSTGRES_DB`/`POSTGRES_USER`
dürfen Defaults behalten.

> **Status: behoben (11.08.2026).** Beide Stellen in `docker-compose.yml`
> nutzen jetzt `${POSTGRES_PASSWORD:?…}`; `docker compose config` scheitert
> ohne gesetztes Passwort (verifiziert) und läuft mit gesetztem Wert.

---

### M1 — CSP mit `unsafe-inline` + `unsafe-eval` (OWASP A03/A05)

`script-src 'self' 'unsafe-inline' 'unsafe-eval'` ist — wie im Caddyfile selbst
dokumentiert — nötig, weil die DC-Laufzeit die Logik-Klasse per `new Function`
auswertet (`support.js:844`). Damit ist die CSP als XSS-Verteidigungslinie
faktisch wirkungslos: jede künftige Injection (z. B. wenn später
nutzergenerierte Inhalte über `POST /spots` dazukommen) würde voll ausgeführt.

**Empfehlung (Aufwand: mittel):** Kompilierter DC-Build (im README bereits als
Ausweg benannt) — dann `'unsafe-eval'` streichen und Inline-Skripte über Nonce
oder Hash zulassen. Bis dahin ergänzen, was heute schon geht:
`object-src 'none'; form-action 'self'` (kostet nichts, schließt Rest-Lücken der
`default-src`-Fallbacks).

### M2 — Lieferkette: keine Pins, kein Scanning, Dependency-Drift (OWASP A06/A08)

* `backend/Dockerfile:11-14` listet die Abhängigkeiten **von Hand** und nur mit
  Untergrenzen (`>=`); `pyproject.toml` wird kopiert, aber nie installiert. Jeder
  Build zieht andere Versionen; eine neue Abhängigkeit im `pyproject` erreicht
  das Image nie (Drift ist vorprogrammiert).
* Kein Lockfile, keine Hash-Pins, kein `pip-audit`/Dependabot/Renovate, kein
  `.github/`-CI.
* Vendored Frontend-Bibliotheken (React 18.3.1, Leaflet 1.9.4) sind aktuell, aber
  ohne dokumentierten Update-Prozess.
* Basisimages (`python:3.12-slim`, `postgis/postgis:16-3.4`, `caddy:2-alpine`)
  ohne Digest-Pin.

**Empfehlung (Aufwand: mittel):** Im Dockerfile `pip install .` aus dem
`pyproject` heraus, dazu ein Lockfile (`uv lock`/`pip-compile --generate-hashes`);
CI mit `pip-audit` + Dependabot; Vendor-Versionen im README bereits notiert —
einen Check dafür in die Tests aufnehmen.

### M3 — `bbox`-Validierung unvollständig: `inf` → HTTP 500 (Robustheit)

`routes.py:249` akzeptiert `float("inf")`/`float("nan")` klaglos.
`render_overlay` fängt NaN als `ValueError` (→ 400 mit interner Meldung
„cannot convert float NaN to integer"), aber **`inf` wirft `OverflowError`**, den
niemand fängt (verifiziert) → unbehandelter 500er inkl. Traceback im Log. Kein
Sicherheitsproblem im engen Sinn, aber ein von außen triggerbarer Serverfehler
und ein Alarmrauschen-Generator.

**Empfehlung (Aufwand: klein):** Nach dem Parsen prüfen:
`all(math.isfinite(v) for v in parsed)`, Wertebereiche (±90/±180) und
`lat_min < lat_max`, `lon_min < lon_max` — sonst 400 mit neutraler Meldung.

> **Status: behoben (11.08.2026).** `_parse_bbox()` in `routes.py` prüft
> Anzahl, Endlichkeit, Wertebereiche und Ordnung und antwortet einheitlich
> mit 400. Tests: `test_api_validation.py`.

### M4 — Container-Härtung ausbaufähig (OWASP A05)

Es fehlen: `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`,
`read_only: true` (API/Worker brauchen nur `/data` und `/tmp` beschreibbar),
Speicher-/CPU-Limits (`mem_limit`, `cpus`) und Log-Rotation (siehe H1). Gerade
Ressourcen-Limits sind die zweite Verteidigungslinie hinter H2: ein
durchdrehender Prozess darf nicht den Host mitnehmen.

**Empfehlung (Aufwand: klein):** Die genannten Optionen je Service ergänzen;
für Postgres `read_only` weglassen.

### M5 — Race zwischen Prune und Auslieferung → 500er (Logikfehler)

`prune_old_runs()` löscht Laufverzeichnisse, während `/clouds` bzw.
`overlay.png` zwischen DB-Abfrage (`forecast_field_current`) und `np.load` genau
diese Dateien öffnen können: `field.path.stat()` in `clouds.py:110` wirft dann
`FileNotFoundError` → 500. Fenster ist klein (Prune läuft nur nach neuem Lauf),
aber am Ereignistag mit hoher Anfragerate wird jedes Fenster getroffen.
Zusätzlich hält der `lru_cache` (64 Einträge) memmaps gelöschter Dateien offen —
der Plattenplatz wird erst bei Cache-Verdrängung frei.

**Empfehlung (Aufwand: klein):** `FileNotFoundError`/`OSError` in
`point_forecast`/`render_overlay` fangen und wie „kein Feld" behandeln
(Retry auf den dann aktuellen Lauf oder 404/`forecast: null`); nach dem Prune
`_load.cache_clear()` aufrufen.

### M6 — `preconnect` an OSM auf jeder Seite (Datenschutz)

`Sofi.dc.html:16` öffnet beim Laden **jeder** Seite eine Verbindung zu
`tile.openstreetmap.org` — auch für Besucher, die nie eine Karte sehen. Der
TLS-Handshake überträgt IP und (per SNI) den Zielhost; OSM sieht also jeden
Seitenbesuch, nicht nur Kartennutzung.

**Empfehlung (Aufwand: eine Zeile):** `preconnect` entfernen (die Kacheln laden
ohnehin erst mit der Karte; der gesparte Handshake ist den Datenabfluss nicht
wert) oder dynamisch erst beim Karteninitialisieren setzen.

> **Status: behoben (11.08.2026).** `preconnect` aus `Sofi.dc.html` entfernt;
> die Verbindung zu OSM entsteht erst mit der tatsächlichen Karteninitialisierung.

### M7 — Legacy-Datei mit unpkg-Referenzen wird öffentlich ausgeliefert

`frontend/SoFi 2026.dc.html` (die ältere Fassung) lädt Leaflet von
`unpkg.com` (Zeile 13/14) und CARTO-Kacheln direkt. Caddy liefert die Datei
unter `/SoFi%202026.dc.html` aus. Die CSP blockiert die unpkg-Skripte zwar
aktuell, aber: die Seite ist kaputt statt geschützt, sie unterläuft die
„ein Fremdhost"-Zusage, sobald jemand die CSP lockert, und sie verwirrt jeden
Crawler.

**Empfehlung (Aufwand: klein):** Datei aus dem ausgelieferten Verzeichnis
entfernen (oder in einen nicht gemounteten Ordner `archive/` verschieben).

> **Status: behoben (11.08.2026).** Nach `archive/SoFi 2026.dc.html`
> verschoben — Caddy mountet nur `./frontend`, die Datei wird nicht mehr
> ausgeliefert.

### M8 — Monitoring/Alerting fehlt (OWASP A09)

Es gibt Healthchecks, aber nichts, das am 12.8. jemanden weckt: keine
Fehlerraten-Metriken, kein Alarm bei `forecast_run`-Stillstand (der Worker
loggt nur), kein Uptime-Check. Der Health-Endpunkt liefert die nötigen Daten
bereits (`forecast_run`-Alter!).

**Empfehlung (Aufwand: klein):** Externer Uptime-Monitor auf `/api/v1/health`
mit Alarm bei `status != ok` **oder** `forecast_run` älter als ~6 h.

---

### N1 — `Permissions-Policy`-Header fehlt

Kostenlose Härtung: `Permissions-Policy "geolocation=(), camera=(), microphone=(), payment=(), usb=()"` im Caddy-Header-Block. Die Seite nutzt bewusst keine
Browser-Geolocation — das darf der Header festschreiben.

### N2 — Dedup-Logik der Ortssuche verliert Orte (Logikfehler)

`geocode.py:76`: Duplikate werden über `(name, int(lat*100))` erkannt — **ohne
Längengrad**. Zwei gleichnamige Orte auf ähnlicher Breite, aber hunderte
Kilometer auseinander (bei „Neustadt" realistisch), verschmelzen zu einem
Treffer. Fix: `(name, round(lat, 2), round(lon, 2))`.

### N3 — Koordinatenpräzision übererfüllt (Datenminimierung)

`api.js:80` sendet `lat.toFixed(5)` (≈ 1 m) an `/clouds`. Das ICON-D2-Gitter
löst 2,2 km auf — 3 Nachkommastellen (≈ 100 m) liefern identische Ergebnisse
und schreiben weniger präzise Standorte in etwaige Logs. Gleiches gilt für
`/circumstances`.

### N4 — Keine Integritätsprüfung der GeoNames-/DWD-Downloads (OWASP A08)

Seed und Ingest vertrauen TLS allein; Checksummen/Größenlimits fehlen
(`bz2.decompress` und `zipfile` arbeiten unbegrenzt im Speicher). Risiko gering
(vertrauenswürdige Quellen, strikte Parser dahinter), aber ein Größenlimit vor
dem Dekomprimieren ist billig.

### N5 — `--proxy-headers` ohne `--forwarded-allow-ips` (Dokumentationslücke)

Uvicorn ignoriert `X-Forwarded-For` von Caddy (Default vertraut nur
127.0.0.1) — die API sieht als Client stets die Caddy-IP. Datenschutzfreundlich,
aber wer später **in der API** nach IP limitieren will, wundert sich. Entweder
die Option entfernen (ehrlicher) oder den Docker-Netzbereich eintragen und das
Verhalten dokumentieren. Rate-Limiting gehört ohnehin an den Caddy (H2).

### N6 — Keine API-Tests für die Fehlerpfade

`tests/` prüft Eclipse-Mathematik, GRIB2 und Normalisierung — aber keinen
Endpunkt. Mindestens H3 (LIKE-Escaping) und M3 (bbox) verdienen Regressionstests
über `fastapi.testclient`.

### N7 — OpenAPI-Doku öffentlich

`/api/v1/docs` und `openapi.json` sind erreichbar. Bei einer bewusst
öffentlichen, lesenden API vertretbar — Entscheidung nur dokumentieren. Wer sie
abschalten will: `docs_url=None, openapi_url=None` in `main.py`.

---

## 4. OWASP-Top-10-Abdeckung (2021)

| # | Kategorie | Befund |
| --- | --- | --- |
| A01 | Broken Access Control | n/a — keine Accounts, GET-only, nur öffentliche Daten. Beim geplanten `POST /spots` neu bewerten (editToken-Konzept, Moderation — die api-spec benennt das bereits). |
| A02 | Cryptographic Failures | **K1** — kein TLS/HSTS im Stack. |
| A03 | Injection | SQL parametrisiert ✔; **H3** LIKE-Wildcards; XSS über React escaped ✔, aber CSP als zweite Linie schwach (**M1**). |
| A04 | Insecure Design | **H2** — keine Lastabwehr für den vorhersehbaren Spitzentag. |
| A05 | Security Misconfiguration | **H4** Default-Passwort; **M4** Container-Härtung; **N1** Permissions-Policy; fehlende Header nach K1. |
| A06 | Vulnerable & Outdated Components | **M2** — keine Pins, kein Scanning, Dockerfile-Drift. |
| A07 | Identification & Authentication | n/a — keine Authentisierung vorhanden oder nötig. |
| A08 | Software & Data Integrity | GRIB2-Signaturprüfung vorbildlich ✔; **M2** (keine Hash-Pins), **N4** (Download-Integrität). |
| A09 | Logging & Monitoring | **H1** — zu *viel* (PII in Logs), zugleich **M8** — zu *wenig* (kein Alerting). |
| A10 | SSRF | n/a — keine nutzergesteuerten URLs ✔. |

## 5. Datenschutz-Bewertung (DSGVO)

**Verarbeitete personenbezogene Daten:** IP-Adressen (Logs, OSM-Kachelabrufe),
Standort-Suchbegriffe und Koordinaten (Query-Strings serverseitig, Logs),
Sprachpräferenz (localStorage, rein clientseitig).

* Die Architektur ist überdurchschnittlich: keine Cookies, kein Consent-Banner
  nötig (localStorage-Sprachwahl ist funktional i. S. v. §25 (2) TDDDG), Suche
  und Rechnung ohne Dritte, ein einziger dokumentierter Fremdhost.
* Die drei Lücken: **Transportverschlüsselung (K1)**, **Rechtstexte (K2)**,
  **Log-Datenminimierung (H1)**. Alle drei sind Betriebs-, nicht Codefragen.
* OSM-Kacheln: Empfängerin ist die OpenStreetMap Foundation (UK —
  Angemessenheitsbeschluss vorhanden). In die Datenschutzerklärung aufnehmen;
  langfristig eliminiert ein selbst gehosteter Vektorkachel-Satz (Protomaps/
  PMTiles, einmalig ~100 GB Europa bzw. ~10 GB Deutschland) den letzten
  Fremdhost — dann wäre die Seite vollständig kontaktfrei. Das löst zugleich
  das im README dokumentierte OSM-Lastspitzen-Risiko.
* **M6** (preconnect) und **N3** (Koordinatenpräzision) sind kleine, billige
  Datenminimierungs-Gewinne.

## 6. Priorisierter Maßnahmenplan

**Sofort (vor dem 12.8., zusammen < 1 Tag):**

1. ~~TLS aktivieren bzw. Terminierung klären + HSTS (K1)~~ ✔ umgesetzt —
   im Deployment `SOFI_DOMAIN`, `WEB_PORT=80`, `WEB_TLS_PORT=443` setzen
2. Impressum + Datenschutzerklärung einspielen (K2)
3. Query-Strings aus Caddy-Log, `--no-access-log` für Uvicorn, Log-Rotation (H1)
4. ~~LIKE-Escaping in `geocode.search()` (H3)~~ ✔ erledigt
5. ~~`POSTGRES_PASSWORD` fail-hard (H4)~~ ✔ erledigt
6. Rate-Limit für `/geocode` + `overlay.png`, Overlay-Cache/ETag (H2)
7. Uptime-Alarm auf `/health` mit `forecast_run`-Alter (M8)
8. ~~Legacy-HTML aus dem Webroot (M7), preconnect raus (M6)~~ ✔ erledigt

**Zeitnah (nächste Wochen):**

9. ~~bbox-Validierung inkl. `inf`/`nan` (M3) + Regressionstests~~ ✔ erledigt
   (Endpunkt-Tests gegen laufende Instanz stehen weiter aus, N6)
10. Prune-Race abfangen, Cache leeren (M5)
11. Container-Härtung: cap_drop, no-new-privileges, Limits (M4)
12. Dockerfile auf `pip install .` + Lockfile, pip-audit/Dependabot in CI (M2)
13. `object-src 'none'; form-action 'self'`, Permissions-Policy (M1/N1)

**Mittelfristig:**

14. Kompilierter DC-Build → `unsafe-eval`/`unsafe-inline` streichen (M1)
15. Selbst gehostete Kacheln → null Fremdhosts, kein OSM-Lastrisiko
16. Dedup-Fix Ortssuche (N2), Koordinaten runden (N3), Download-Limits (N4)
17. Vor `POST /spots`: Auth-/Moderations-/Rate-Limit-Konzept (A01/A07)

---

*Methodik: vollständige manuelle Durchsicht aller Quelldateien (Backend, Frontend,
Infrastruktur, Schema, Datenpipelines), Verifikation der Einzelbefunde H3 und M3
durch Ausführung der betroffenen Codepfade, Abgleich gegen OWASP Top 10 (2021),
OWASP API Security Top 10 und DSGVO-Anforderungen. Keine dynamischen Tests gegen
eine laufende Instanz.*
