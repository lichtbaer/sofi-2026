// Erzeugt die Referenzwerte, gegen die app/eclipse.py getestet wird.
// Die Wahrheit ist frontend/eclipse.js — der Python-Port darf nicht driften.
//
//   node backend/scripts/golden_eclipse.mjs > backend/tests/golden_eclipse.json

import { localCircumstances } from '../../frontend/eclipse.js';

const POINTS = [
  ['Flensburg', 54.7937, 9.4469],
  ['Berlin', 52.52, 13.405],
  ['Köln', 50.9375, 6.9603],
  ['Frankfurt am Main', 50.1109, 8.6821],
  ['München', 48.1351, 11.582],
  ['Freiburg im Breisgau', 47.999, 7.8421],
  ['Sylt', 54.9079, 8.3038],
  ['Brocken', 51.7991, 10.6156],
  ['Zugspitze', 47.4211, 10.9853],
];

const iso = (d) => new Date(d).toISOString().replace('.000Z', 'Z');

const cases = POINTS.map(([name, lat, lon]) => {
  const c = localCircumstances(lat, lon, 0);
  return {
    name, lat, lon, visible: c.visible,
    maximum: {
      time: iso(c.max.date),
      altitude: +c.max.alt.toFixed(6),
      azimuth: +c.max.az.toFixed(6),
      obscuration: +c.max.obs.toFixed(8),
      magnitude: +c.max.mag.toFixed(8),
    },
    c1: { time: iso(c.c1.date), altitude: +c.c1.alt.toFixed(6) },
    c4: { time: iso(c.c4.date), altitude: +c.c4.alt.toFixed(6) },
    sunset: c.sunset ? iso(c.sunset.date) : null,
    endsAtSunset: c.endsAtSunset,
  };
});

console.log(JSON.stringify({
  source: 'frontend/eclipse.js',
  generated: 'node backend/scripts/golden_eclipse.mjs',
  cases,
}, null, 2));
