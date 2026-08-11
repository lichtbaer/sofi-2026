// Zugriff auf das eigene Backend. Gleicher Origin, deshalb keine CORS-Sonderwege.
//
// Jede Funktion wirft bei Fehlern — der Aufrufer entscheidet, ob er auf die
// lokalen Ersatzdaten zurückfällt. Am Ereignisabend soll ein überlastetes
// Backend die Seite nicht mitnehmen: Kontaktzeiten und Isolinien rechnet
// eclipse.js ohnehin im Browser.

import { API_BASE } from './config.js';

const TIMEOUT_MS = 8000;

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function get(path, params = {}, { signal } = {}) {
  const url = new URL(`${API_BASE}${path}`, location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  }

  // Eigenes Zeitlimit, zusätzlich zum Abbruch durch den Aufrufer.
  const timer = new AbortController();
  const timeout = setTimeout(() => timer.abort(), TIMEOUT_MS);
  const onAbort = () => timer.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(url, { signal: timer.signal, headers: { accept: 'application/json' } });
    if (!response.ok) {
      throw new ApiError(`${path} antwortete ${response.status}`, response.status);
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', onAbort);
  }
}

/* ── Ortssuche ─────────────────────────────────────────────────────────────
   Kleiner Cache je Suchbegriff: beim Tippen und Löschen wird derselbe Präfix
   mehrfach angefragt, und die Ergebnisse ändern sich zur Laufzeit nicht.   */

const geocodeCache = new Map();
const GEOCODE_CACHE_MAX = 60;

export async function geocode(query, options = {}) {
  const q = query.trim();
  if (!q) return [];

  const cached = geocodeCache.get(q.toLowerCase());
  if (cached) return cached;

  const { results } = await get('/geocode', { q, limit: options.limit ?? 7 }, options);
  const places = results.map((r) => ({
    name: r.name,
    plz: r.plz,
    state: r.state,
    lat: r.lat,
    lon: r.lon,
    elevation: r.elevation,
  }));

  if (geocodeCache.size >= GEOCODE_CACHE_MAX) {
    geocodeCache.delete(geocodeCache.keys().next().value);
  }
  geocodeCache.set(q.toLowerCase(), places);
  return places;
}

/* ── Wolken ────────────────────────────────────────────────────────────────
   `at_maximum` ist bereits auf die lokale Maximumszeit interpoliert; das
   Backend rechnet dafür dieselben Besselschen Elemente wie eclipse.js.     */

/* Drei Nachkommastellen, nicht fünf: das sind rund 110 m, und das ICON-D2-Gitter
   löst 2,2 km auf. Die bilineare Interpolation im Backend verschiebt sich damit um
   etwa 5 % einer Maschenweite — im Ergebnis nicht darstellbar. Fünf Stellen wären
   rund ein Meter gewesen und hätten nach einem Klick auf „Mein Standort" die
   Geräteposition in die Serverprotokolle geschrieben. */
export async function clouds(lat, lon, options = {}) {
  const data = await get('/clouds', { lat: lat.toFixed(3), lon: lon.toFixed(3) }, options);
  if (!data.forecast) return null;

  const f = data.forecast;
  return {
    model: f.model,
    runAt: new Date(f.run_at),
    maximumAt: new Date(f.maximum_at),
    atMaximum: sample(f.at_maximum),
    series: f.series.map(sample),
    climatology: data.climatology,
  };
}

function sample(s) {
  return {
    validAt: new Date(s.valid_at),
    total: s.total,
    low: s.low,
    mid: s.mid,
    high: s.high,
    obstruction: s.obstruction,
  };
}

/** Verfügbare Kartenoverlays des jüngsten Laufs. */
export async function cloudOverlays(options = {}) {
  const { overlays } = await get('/clouds/overlays', {}, options);
  return overlays.map((o) => ({
    variable: o.variable,
    validAt: new Date(o.valid_at),
    runAt: new Date(o.run_at),
    url: o.url,
  }));
}

/** Betriebszustand — für einen Hinweis, wenn die Prognose fehlt. */
export async function health(options = {}) {
  return get('/health', {}, options);
}

export { ApiError };
