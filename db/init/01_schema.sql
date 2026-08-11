-- Schema SoFi 2026. Wird vom postgis-Image genau einmal beim Anlegen des
-- Datenverzeichnisses ausgeführt. Änderungen danach über Migrationen.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ── Orte ────────────────────────────────────────────────────────────────────
-- Quelle: GeoNames DE (CC BY 4.0), einmalig eingespielt. Zur Laufzeit wird
-- kein externer Dienst befragt.

CREATE TABLE place (
    id            bigserial PRIMARY KEY,
    geonames_id   bigint UNIQUE NOT NULL,
    -- Anzeigename, bevorzugt der deutsche. GeoNames führt einen Teil der
    -- Großstädte unter dem englischen Exonym („Munich", „Nuremberg"),
    -- andere deutsch („Köln") — der Anzeigename kommt deshalb aus den
    -- alternativen Namen mit isolanguage = de, wenn es einen gibt.
    name          text   NOT NULL,
    feature_code  text   NOT NULL,
    state         text,
    population    integer NOT NULL DEFAULT 0,
    elevation     integer,
    geom          geography(Point, 4326) NOT NULL
);

CREATE INDEX place_geom_idx       ON place USING gist (geom);
CREATE INDEX place_population_idx ON place (population DESC);

-- Alle Schreibweisen eines Ortes, über die er gefunden werden soll:
-- Hauptname, ASCII-Fassung und sämtliche deutschen Alternativnamen.
-- name_key ist diakritikafrei (münchen -> munchen), name_key_alt nutzt die
-- deutsche Umschrift (münchen -> muenchen). Damit findet beide Tippweisen.
CREATE TABLE place_alias (
    place_id     bigint NOT NULL REFERENCES place(id) ON DELETE CASCADE,
    name_key     text   NOT NULL,
    name_key_alt text   NOT NULL
);

CREATE INDEX place_alias_key_idx  ON place_alias (name_key text_pattern_ops);
CREATE INDEX place_alias_alt_idx  ON place_alias (name_key_alt text_pattern_ops);
CREATE INDEX place_alias_trgm_idx ON place_alias USING gin (name_key gin_trgm_ops);
CREATE INDEX place_alias_place_idx ON place_alias (place_id);

CREATE TABLE postal_code (
    id       bigserial PRIMARY KEY,
    code     text NOT NULL,
    name     text NOT NULL,
    name_key text NOT NULL,
    state    text,
    geom     geography(Point, 4326) NOT NULL,
    UNIQUE (code, name)
);

CREATE INDEX postal_code_code_idx ON postal_code (code text_pattern_ops);
CREATE INDEX postal_code_geom_idx ON postal_code USING gist (geom);

-- ── Prognosefelder ──────────────────────────────────────────────────────────
-- Die Rasterdaten selbst liegen als uint8-Arrays auf dem Volume; Postgres hält
-- nur die Metadaten. Ein Raster gehört nicht in eine Zeilenspeicher-Datenbank,
-- und der Punktzugriff ist als memmap um Größenordnungen schneller.

CREATE TABLE forecast_run (
    id           bigserial PRIMARY KEY,
    model        text        NOT NULL,
    run_at       timestamptz NOT NULL,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    UNIQUE (model, run_at)
);

CREATE TABLE forecast_field (
    id         bigserial   PRIMARY KEY,
    run_id     bigint      NOT NULL REFERENCES forecast_run(id) ON DELETE CASCADE,
    variable   text        NOT NULL,
    valid_at   timestamptz NOT NULL,
    path       text        NOT NULL,
    ni         integer     NOT NULL,
    nj         integer     NOT NULL,
    lat_first  double precision NOT NULL,
    lon_first  double precision NOT NULL,
    dlat       double precision NOT NULL,
    dlon       double precision NOT NULL,
    nodata     smallint    NOT NULL DEFAULT 255,
    UNIQUE (run_id, variable, valid_at)
);

CREATE INDEX forecast_field_lookup_idx ON forecast_field (variable, valid_at);

-- Nur abgeschlossene Läufe werden ausgeliefert: finished_at IS NOT NULL.
CREATE VIEW forecast_field_current AS
SELECT f.*, r.model, r.run_at
FROM forecast_field f
JOIN forecast_run r ON r.id = f.run_id
WHERE r.finished_at IS NOT NULL
  AND r.run_at = (SELECT max(run_at) FROM forecast_run
                  WHERE model = r.model AND finished_at IS NOT NULL);
