// Ortsdatenbank (Demo-Auszug als Rückfall) und die feste Standortliste.
// Horizontprofile kommen aus /api/v1/horizon — siehe api-spec.md.

export const CITIES = [
  ['Aachen', 50.7753, 6.0839, '52062'], ['Augsburg', 48.3705, 10.8978, '86150'],
  ['Berlin', 52.52, 13.405, '10115'], ['Bielefeld', 52.0302, 8.5325, '33602'],
  ['Bonn', 50.7374, 7.0982, '53111'], ['Braunschweig', 52.2689, 10.5268, '38100'],
  ['Bremen', 53.0793, 8.8017, '28195'], ['Chemnitz', 50.8278, 12.9214, '09111'],
  ['Cottbus', 51.7563, 14.3329, '03046'], ['Darmstadt', 49.8728, 8.6512, '64283'],
  ['Dortmund', 51.5136, 7.4653, '44135'], ['Dresden', 51.0504, 13.7373, '01067'],
  ['Duisburg', 51.4344, 6.7623, '47051'], ['Düsseldorf', 51.2277, 6.7735, '40213'],
  ['Erfurt', 50.9848, 11.0299, '99084'], ['Essen', 51.4556, 7.0116, '45127'],
  ['Flensburg', 54.7937, 9.4469, '24937'], ['Frankfurt am Main', 50.1109, 8.6821, '60311'],
  ['Freiburg im Breisgau', 47.999, 7.8421, '79098'], ['Garmisch-Partenkirchen', 47.4917, 11.0954, '82467'],
  ['Göttingen', 51.5413, 9.9158, '37073'], ['Hamburg', 53.5511, 9.9937, '20095'],
  ['Hannover', 52.3759, 9.732, '30159'], ['Heidelberg', 49.3988, 8.6724, '69117'],
  ['Kaiserslautern', 49.4401, 7.7491, '67655'], ['Karlsruhe', 49.0069, 8.4037, '76133'],
  ['Kassel', 51.3127, 9.4797, '34117'], ['Kiel', 54.3233, 10.1228, '24103'],
  ['Koblenz', 50.3569, 7.5886, '56068'], ['Köln', 50.9375, 6.9603, '50667'],
  ['Konstanz', 47.6603, 9.1758, '78462'], ['Leipzig', 51.3397, 12.3731, '04109'],
  ['Lübeck', 53.8655, 10.6866, '23552'], ['Magdeburg', 52.1205, 11.6276, '39104'],
  ['Mainz', 49.9929, 8.2473, '55116'], ['Mannheim', 49.4875, 8.466, '68159'],
  ['München', 48.1351, 11.582, '80331'], ['Münster', 51.9607, 7.6261, '48143'],
  ['Norderney', 53.7078, 7.155, '26548'], ['Nürnberg', 49.4521, 11.0767, '90402'],
  ['Oldenburg', 53.1435, 8.2146, '26121'], ['Osnabrück', 52.2799, 8.0472, '49074'],
  ['Passau', 48.5665, 13.4312, '94032'], ['Potsdam', 52.3906, 13.0645, '14467'],
  ['Regensburg', 49.0134, 12.1016, '93047'], ['Rostock', 54.0924, 12.0991, '18055'],
  ['Saarbrücken', 49.2402, 6.9969, '66111'], ['Schwerin', 53.6355, 11.4012, '19053'],
  ['Stuttgart', 48.7758, 9.1829, '70173'], ['Sylt (Westerland)', 54.9079, 8.3038, '25980'],
  ['Trier', 49.7496, 6.6371, '54290'], ['Ulm', 48.4011, 9.9876, '89073'],
  ['Wiesbaden', 50.0782, 8.2398, '65183'], ['Würzburg', 49.7913, 9.9534, '97070'],
].map(([name, lat, lon, plz]) => ({ name, lat, lon, plz }));

export function geocode(q) {
  const s = q.trim().toLowerCase();
  if (!s) return [];
  const norm = (x) => x.toLowerCase().replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 'ss');
  const t = norm(s);
  return CITIES
    .map((c) => {
      const n = norm(c.name);
      let rank = -1;
      if (c.plz.startsWith(s)) rank = 0;
      else if (n.startsWith(t)) rank = 1;
      else if (n.includes(t)) rank = 2;
      return { ...c, rank };
    })
    .filter((c) => c.rank >= 0)
    .sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name))
    .slice(0, 7);
}

/* ── Beobachtungsstandorte ────────────────────────────────────────────────────
   Reale Orte und Koordinaten. Der Horizont steht hier *nicht* mehr: er kommt
   aus /api/v1/horizon, gerechnet aus Copernicus GLO-30.

   Bis 2026-08-11 stand hier ein Feld `hz` und darunter eine Funktion
   `horizonProfile()`, die aus drei Sinustermen ein Profil erzeugte. Das sah
   im Diagramm aus wie eine Geländesilhouette, ging mit 0,42 in den Score ein
   und ergab für alle zwölf Standorte „sicher frei" — weil der Rauschterm bei
   null geklemmt war und damit gar nicht verdecken konnte. Ein erfundener Wert
   in der Form eines Messergebnisses ist schlechter als eine Lücke; wenn die
   API nichts liefert, zeigt die Seite jetzt nichts.

   `cloud` ist weiterhin ein Platzhalter (Klimatologie, CM SAF fehlt noch) und
   als solcher gekennzeichnet.

   Vier Koordinaten lagen neben dem Gipfel und sind gegen das Höhenmodell
   nachgezogen: Hesselberg lag 93 m tiefer am Hang und wurde deshalb als
   „verdeckt" bewertet — bei einem freistehenden Zeugenberg mit Rundumsicht.
   Das Sinusprofil hat solche Fehler nie auffallen lassen, weil es die
   Koordinate gar nicht benutzt hat.                                        */
export const SITES = [
  { id: 'brocken', name: 'Brocken', region: 'Harz, Sachsen-Anhalt', lat: 51.7991, lon: 10.6156, h: 1141, cloud: 0.62, access: 'frei', accessNote: 'Nationalpark, Brockenbahn bis zum Gipfel, kein Pkw-Zugang.' },
  { id: 'feldberg', name: 'Feldberg', region: 'Schwarzwald, Baden-Württemberg', lat: 47.8739, lon: 8.0044, h: 1493, cloud: 0.48, access: 'frei', accessNote: 'Naturschutzgebiet – Wege nicht verlassen.' },
  { id: 'wasserkuppe', name: 'Wasserkuppe', region: 'Rhön, Hessen', lat: 50.4982, lon: 9.936, h: 950, cloud: 0.5, access: 'frei', accessNote: 'Sternenpark Rhön, große Freiflächen, Parkplatz am Gipfel.' },
  { id: 'kahlerasten', name: 'Kahler Asten', region: 'Sauerland, NRW', lat: 51.1817, lon: 8.4886, h: 841, cloud: 0.55, access: 'frei', accessNote: 'Hochheide, markierte Wege.' },
  { id: 'hohepeissenberg', name: 'Hoher Peißenberg', region: 'Oberbayern', lat: 47.8009, lon: 11.0111, h: 988, cloud: 0.45, access: 'frei', accessNote: 'Wetterwarte, Aussichtsterrasse frei zugänglich.' },
  { id: 'fichtelberg', name: 'Fichtelberg', region: 'Erzgebirge, Sachsen', lat: 50.4283, lon: 12.9542, h: 1215, cloud: 0.58, access: 'frei', accessNote: 'Seilbahn und Straße zum Gipfel.' },
  { id: 'hesselberg', name: 'Hesselberg', region: 'Mittelfranken, Bayern', lat: 49.0686, lon: 10.5276, h: 689, cloud: 0.47, access: 'frei', accessNote: 'Freistehender Zeugenberg, Rundumsicht.' },
  { id: 'kalmit', name: 'Kalmit', region: 'Pfälzerwald, Rheinland-Pfalz', lat: 49.3188, lon: 8.0823, h: 673, cloud: 0.44, access: 'frei', accessNote: 'Blick über die Rheinebene nach Westen.' },
  { id: 'stpeterording', name: 'St. Peter-Ording, Strand', region: 'Nordfriesland, Schleswig-Holstein', lat: 54.3, lon: 8.6167, h: 2, cloud: 0.6, access: 'eingeschränkt', accessNote: 'Nationalpark Wattenmeer, Schutzzonen beachten; Strandzufahrt kostenpflichtig.' },
  { id: 'darsser', name: 'Darßer Ort', region: 'Vorpommern, Mecklenburg-Vorpommern', lat: 54.4711, lon: 12.5044, h: 3, cloud: 0.57, access: 'eingeschränkt', accessNote: 'Kernzone Nationalpark Vorpommersche Boddenlandschaft – Betretungsregeln prüfen.' },
  { id: 'helgoland', name: 'Helgoland, Oberland', region: 'Nordsee, Schleswig-Holstein', lat: 54.1817, lon: 7.885, h: 58, cloud: 0.63, access: 'frei', accessNote: 'Freier Seehorizont nach Westen; Anreise nur per Schiff.' },
  { id: 'hohentwiel', name: 'Hohentwiel', region: 'Hegau, Baden-Württemberg', lat: 47.7643, lon: 8.8186, h: 686, cloud: 0.46, access: 'eingeschränkt', accessNote: 'Festungsruine, Öffnungszeiten und Eintritt beachten.' },
];

