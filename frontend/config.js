// Betriebsknöpfe des Frontends. Bewusst eine eigene Datei: ein Wechsel des
// Kachelanbieters soll die von der DC-Tooling verwaltete HTML nicht anfassen.

/** Basis der eigenen API. Gleicher Origin, deshalb relativ. */
export const API_BASE = '/api/v1';

/* ── Kartenkacheln ───────────────────────────────────────────────────────────
   Der einzige Fremdhost der Seite. Alles andere — Leaflet, Schriften,
   Ortssuche, Wolkendaten — kommt vom eigenen Server.

   OSMs Kachelserver laufen auf Spenden und sichern nichts zu: „Availability is
   best-effort: there is no SLA or guarantee. We may block access, without
   notice, if your usage degrades the service." Für den Abend des 12.8. mit
   bundesweiter Lastspitze ist das ein Risiko. Zum Umschalten reicht es, unten
   einen anderen Eintrag zu aktivieren.

   Die Policy verlangt außerdem einen gültigen Referer — siehe die
   Referrer-Policy in web/Caddyfile — und sichtbare Namensnennung.           */

export const BASEMAPS = {
  osm: {
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
    // Standardkacheln gibt es nur hell. „dunkel" entsteht über einen
    // CSS-Filter auf der Kachelebene — kein echtes dunkles Kartenbild,
    // aber unter Isolinien und Wolkenoverlay ausreichend ruhig.
    darkViaFilter: true,
  },
  carto: {
    url: 'https://{s}.basemaps.cartocdn.com/{style}/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd',
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap-Mitwirkende, &copy; CARTO',
    styles: { hell: 'light_all', dunkel: 'dark_all' },
    darkViaFilter: false,
  },
};

/** Aktiver Anbieter. */
export const BASEMAP = BASEMAPS.osm;

/** Liefert URL-Vorlage und Leaflet-Optionen für den gewünschten Stil. */
export function basemapLayer(style = 'hell') {
  const dark = style === 'dunkel';
  const options = {
    maxZoom: BASEMAP.maxZoom,
    attribution: BASEMAP.attribution,
    ...(BASEMAP.subdomains ? { subdomains: BASEMAP.subdomains } : {}),
    ...(dark && BASEMAP.darkViaFilter ? { className: 'basemap-dark' } : {}),
  };
  const url = BASEMAP.styles
    ? BASEMAP.url.replace('{style}', BASEMAP.styles[style] || BASEMAP.styles.hell)
    : BASEMAP.url;
  return { url, options };
}
