// Lokale Umstände der totalen Sonnenfinsternis 2026-08-12 (in Deutschland partiell).
// Polynomiale Besselsche Elemente: NASA/GSFC Five Millennium Canon (Espenak), t0 = 2026 Aug 12, 18.000 TDT.
const DT = 75.4;                     // ΔT in Sekunden
const TANF1 = 0.0046141, TANF2 = 0.0045911;
const E = {
  x:  [0.4755140, 0.5189249, -0.0000773, -0.0000080],
  y:  [0.7711830, -0.2301680, -0.0001246, 0.0000038],
  d:  [14.7966700, -0.0120650, -0.0000030, 0],
  l1: [0.5379550, 0.0000939, -0.0000121, 0],
  l2: [-0.0081420, 0.0000935, -0.0000121, 0],
  mu: [88.747787, 15.003090, 0, 0],
};
const RAD = Math.PI / 180;
const poly = (c, t) => c[0] + c[1] * t + c[2] * t * t + c[3] * t * t * t;
const bess = (t) => ({
  x: poly(E.x, t), y: poly(E.y, t), d: poly(E.d, t),
  l1: poly(E.l1, t), l2: poly(E.l2, t), mu: poly(E.mu, t),
});

export const T0_UTC_MS = Date.UTC(2026, 7, 12, 18, 0, 0);
// t = Stunden nach t0 (TDT)  ->  echte Weltzeit
export const tToDate = (t) => new Date(T0_UTC_MS + (t * 3600 - DT) * 1000);

export function fmtTime(date, withSec = true) {
  return date.toLocaleTimeString('de-DE', {
    timeZone: 'Europe/Berlin', hour: '2-digit', minute: '2-digit',
    ...(withSec ? { second: '2-digit' } : {}),
  });
}

// Überdeckte Fläche zweier Kreise / Sonnenfläche
function areaFrac(d, rs, rm) {
  if (d >= rs + rm) return 0;
  if (d <= rm - rs) return 1;
  if (d <= rs - rm) return (rm * rm) / (rs * rs);
  const a = Math.acos((d * d + rs * rs - rm * rm) / (2 * d * rs));
  const b = Math.acos((d * d + rm * rm - rs * rs) / (2 * d * rm));
  const area = rs * rs * (a - Math.sin(2 * a) / 2) + rm * rm * (b - Math.sin(2 * b) / 2);
  return area / (Math.PI * rs * rs);
}

function observer(lat, lonDeg, hMeters) {
  const u = Math.atan(0.99664719 * Math.tan(lat * RAD));
  return {
    rs: 0.99664719 * Math.sin(u) + (hMeters / 6378140) * Math.sin(lat * RAD),
    rc: Math.cos(u) + (hMeters / 6378140) * Math.cos(lat * RAD),
    lat, lon: lonDeg,
  };
}

// Zustand zum Zeitpunkt t (TDT-Stunden nach t0)
function stateAt(o, t) {
  const e = bess(t);
  const H = (e.mu + o.lon - 0.00417807 * DT) * RAD;
  const d = e.d * RAD, phi = o.lat * RAD;
  const xi = o.rc * Math.sin(H);
  const eta = o.rs * Math.cos(d) - o.rc * Math.cos(H) * Math.sin(d);
  const zeta = o.rs * Math.sin(d) + o.rc * Math.cos(H) * Math.cos(d);
  const du = e.x - xi, dv = e.y - eta;
  const m = Math.hypot(du, dv);
  const L1 = e.l1 - zeta * TANF1, L2 = e.l2 - zeta * TANF2;
  const Rs = (L1 + L2) / 2, Rm = (L1 - L2) / 2;
  // Sonnenstand (Deklination der Schattenachse ≈ Sonnendeklination)
  const north = -Math.cos(d) * Math.cos(H) * Math.sin(phi) + Math.sin(d) * Math.cos(phi);
  const east = -Math.cos(d) * Math.sin(H);
  const up = Math.cos(d) * Math.cos(H) * Math.cos(phi) + Math.sin(d) * Math.sin(phi);
  // Parallaktischer Winkel (für die Darstellung mit Horizont unten)
  const q = Math.atan2(Math.sin(H), Math.tan(phi) * Math.cos(d) - Math.sin(d) * Math.cos(H)) / RAD;
  return {
    t, m, L1, L2, Rs, Rm, du, dv, q,
    // Positionswinkel des Mondmittelpunkts relativ zur Sonne, von Nord über Ost
    pa: (Math.atan2(du, dv) / RAD + 360) % 360,
    mag: (L1 - m) / (L1 + L2),
    obs: areaFrac(m, Rs, Rm),
    alt: Math.asin(up) / RAD,
    az: (Math.atan2(east, north) / RAD + 360) % 360,
  };
}

const sunAlt = (o, t) => stateAt(o, t).alt;

function bisect(f, a, b, iter = 46) {
  let fa = f(a);
  for (let i = 0; i < iter; i++) {
    const mid = (a + b) / 2, fm = f(mid);
    if ((fa < 0) === (fm < 0)) { a = mid; fa = fm; } else { b = mid; }
  }
  return (a + b) / 2;
}

/** Vollständige lokale Umstände. lat/lon in Grad (Ost positiv), h in Metern. */
export function localCircumstances(lat, lon, h = 0) {
  const o = observer(lat, lon, h);
  // Maximum: Minimum von m(t)
  let best = null;
  for (let t = -3; t <= 3; t += 1 / 60) {
    const s = stateAt(o, t);
    if (!best || s.m < best.m) best = s;
  }
  let a = best.t - 1 / 60, b = best.t + 1 / 60;
  for (let i = 0; i < 60; i++) {
    const m1 = a + (b - a) / 3, m2 = b - (b - a) / 3;
    if (stateAt(o, m1).m < stateAt(o, m2).m) b = m2; else a = m1;
  }
  const max = stateAt(o, (a + b) / 2);
  if (max.obs <= 0) return { visible: false, max };

  const gap = (t) => { const s = stateAt(o, t); return s.m - s.L1; };
  const c1 = bisect(gap, max.t - 3, max.t);
  const c4 = bisect(gap, max.t + 3, max.t);

  // Sonnenuntergang: Höhe = -0.833° (Refraktion + Halbmesser)
  let ss = null;
  for (let t = max.t; t <= max.t + 6; t += 1 / 60) {
    if (sunAlt(o, t) < -0.833) { ss = bisect((x) => sunAlt(o, x) + 0.833, t - 1 / 60, t); break; }
  }

  // Verlauf für die Grafik
  const track = [];
  for (let i = 0; i <= 120; i++) {
    const t = c1 + ((c4 - c1) * i) / 120;
    const s = stateAt(o, t);
    track.push({ t, obs: Math.max(0, s.obs), alt: s.alt, date: tToDate(t) });
  }

  return {
    visible: true,
    c1: { t: c1, date: tToDate(c1), alt: sunAlt(o, c1) },
    c4: { t: c4, date: tToDate(c4), alt: sunAlt(o, c4) },
    max: { ...max, date: tToDate(max.t) },
    sunset: ss === null ? null : { t: ss, date: tToDate(ss) },
    // sichtbarer Teil: Finsternis endet visuell mit dem Sonnenuntergang
    endsAtSunset: ss !== null && ss < c4,
    track,
    sample: (t) => stateAt(o, t),
  };
}

/** Nur maximale Obskuration – schnell, für Rastergitter. */
export function maxObscuration(lat, lon) {
  const o = observer(lat, lon, 0);
  let a = -2.5, b = 2.5;
  for (let i = 0; i < 70; i++) {
    const m1 = a + (b - a) / 3, m2 = b - (b - a) / 3;
    if (stateAt(o, m1).m < stateAt(o, m2).m) b = m2; else a = m1;
  }
  return stateAt(o, (a + b) / 2).obs;
}

/* ── Isolinien der Bedeckung (Marching Squares über ein Raster) ────────────── */
export function coverageContours(bbox, step, levels) {
  const [lat0, lon0, lat1, lon1] = bbox;
  const nx = Math.round((lon1 - lon0) / step) + 1;
  const ny = Math.round((lat1 - lat0) / step) + 1;
  const g = [];
  for (let j = 0; j < ny; j++) {
    const row = [];
    for (let i = 0; i < nx; i++) row.push(maxObscuration(lat0 + j * step, lon0 + i * step) * 100);
    g.push(row);
  }
  const out = levels.map((level) => ({ level, segments: [] }));
  const pt = (i, j, i2, j2, va, vb, lv) => {
    const f = (lv - va) / (vb - va);
    return [lat0 + (j + (j2 - j) * f) * step, lon0 + (i + (i2 - i) * f) * step];
  };
  for (let li = 0; li < levels.length; li++) {
    const lv = levels[li];
    for (let j = 0; j < ny - 1; j++) {
      for (let i = 0; i < nx - 1; i++) {
        const v = [g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]];
        const idx = (v[0] > lv ? 1 : 0) | (v[1] > lv ? 2 : 0) | (v[2] > lv ? 4 : 0) | (v[3] > lv ? 8 : 0);
        if (idx === 0 || idx === 15) continue;
        const bot = () => pt(i, j, i + 1, j, v[0], v[1], lv);
        const right = () => pt(i + 1, j, i + 1, j + 1, v[1], v[2], lv);
        const top = () => pt(i + 1, j + 1, i, j + 1, v[2], v[3], lv);
        const left = () => pt(i, j + 1, i, j, v[3], v[0], lv);
        const S = out[li].segments;
        const seg = { 1: [bot, left], 2: [bot, right], 3: [left, right], 4: [right, top],
          6: [bot, top], 7: [left, top], 8: [top, left], 9: [bot, top], 11: [top, right],
          12: [left, right], 13: [bot, right], 14: [bot, left] }[idx];
        if (seg) S.push([seg[0](), seg[1]()]);
        if (idx === 5) { S.push([bot(), right()]); S.push([top(), left()]); }
        if (idx === 10) { S.push([bot(), left()]); S.push([top(), right()]); }
      }
    }
  }
  // Segmente zu Polylinien verketten
  return out.map(({ level, segments }) => {
    const key = (p) => `${p[0].toFixed(4)},${p[1].toFixed(4)}`;
    const used = new Array(segments.length).fill(false);
    const byStart = new Map();
    segments.forEach((s, i) => {
      for (const k of [key(s[0]), key(s[1])]) {
        if (!byStart.has(k)) byStart.set(k, []);
        byStart.get(k).push(i);
      }
    });
    const lines = [];
    for (let i = 0; i < segments.length; i++) {
      if (used[i]) continue;
      used[i] = true;
      const line = [segments[i][0], segments[i][1]];
      for (const dir of [1, 0]) {
        for (;;) {
          const end = dir ? line[line.length - 1] : line[0];
          const cand = (byStart.get(key(end)) || []).find((k) => !used[k]);
          if (cand === undefined) break;
          used[cand] = true;
          const s = segments[cand];
          const next = key(s[0]) === key(end) ? s[1] : s[0];
          if (dir) line.push(next); else line.unshift(next);
        }
      }
      if (line.length > 2) lines.push(line);
    }
    return { level, lines };
  });
}
