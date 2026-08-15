/* Hero-Flug-Konfiguration (DE) — mountet die Scroll-World-Engine auf #world. */
(function () {
  var el = document.getElementById('world');
  if (!el || !window.mountScrollWorld) return;
  var YT = 'https://www.youtube.com/@OrphicOS-deutsch';
  mountScrollWorld(el, {
    hint: 'Scrollen zum Einfliegen',
    diveScroll: 1.3,
    connScroll: 0.9,
    sections: [
      {
        id: 'maschinen', label: 'Die Maschinen', accent: '#d94f2b',
        still: '/assets/world/scene1.webp',
        clip: '/assets/world/dive1.mp4', clipMobile: '/assets/world/dive1-m.mp4',
        scroll: 1.6, linger: 0.35,
        eyebrow: 'OrphicOS · Lokale KI für Unternehmen',
        title: 'Lokale KI auf deinen Rechnern — nicht in der Cloud.',
        body: 'Wir richten ChatGPT-ähnliche KI bei dir ein. Daten bleiben im Haus. Wiederkehrende Aufgaben automatisieren wir, wenn du das willst.',
        tags: ['Lokal', 'Keine Cloud', 'Automatisierung optional']
      },
      {
        id: 'schreibtisch', label: 'Dein Schreibtisch', accent: '#d94f2b',
        still: '/assets/world/scene2.webp',
        clip: '/assets/world/dive2.mp4', clipMobile: '/assets/world/dive2-m.mp4',
        eyebrow: 'Installation',
        title: 'Wir richten sie dort ein, wo du schon arbeitest.',
        body: 'Auf deiner Infrastruktur — Desktops, Server, deine Apps. Kein Cloud-Konto, keine Datenleitung nach draußen.',
        tags: ['Deine Hardware', 'Deine Apps']
      },
      {
        id: 'team', label: 'Das Team', accent: '#d94f2b',
        still: '/assets/world/scene3.webp',
        clip: '/assets/world/dive3.mp4', clipMobile: '/assets/world/dive3-m.mp4',
        eyebrow: 'Optional',
        title: 'Sechs Abteilungen. Automatisierung nur, wenn du willst.',
        body: 'Marketing, Recherche, Vertrieb, Assistenz, YouTube, Support — wir automatisieren die Abläufe, die du uns gibst. Oder wir bleiben bei lokaler KI zum Arbeiten.',
        tags: ['Marketing', 'Recherche', 'Vertrieb', 'Assistenz', 'YouTube', 'Support']
      },
      {
        id: 'garantie', label: 'Die Garantie', accent: '#d94f2b',
        still: '/assets/world/scene4.webp',
        clip: '/assets/world/dive4.mp4', clipMobile: '/assets/world/dive4-m.mp4',
        scroll: 1.7, linger: 0.4,
        eyebrow: 'Die Garantie',
        title: 'Nichts verlässt jemals das Gebäude.',
        body: 'Deine Verträge, Kundendaten und dein Quellcode bleiben auf deiner Festplatte. Leistung und Vertraulichkeit — ohne Kompromiss.',
        cta: {
          primary: { label: 'Enterprise-Beratung buchen', href: 'https://t.me/OrphicOS' },
          secondary: { label: 'RUF DIREKT AN', href: 'tel:+4915678383760' }
        }
      }
    ],
    connectors: ['/assets/world/conn12.mp4', '/assets/world/conn23.mp4', '/assets/world/conn34.mp4'],
    connectorsMobile: ['/assets/world/conn12-m.mp4', '/assets/world/conn23-m.mp4', '/assets/world/conn34-m.mp4']
  });
})();
