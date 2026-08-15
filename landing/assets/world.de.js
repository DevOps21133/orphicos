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
        eyebrow: 'OrphicOS · Autonome KI-Mitarbeiter für Unternehmen',
        title: 'Ein KI-Mitarbeiter, der die Arbeit erledigt — auf deinen Rechnern, nicht in der Cloud.',
        body: 'OrphicOS führt echte Geschäftsabläufe von Anfang bis Ende in deinen eigenen Apps aus. Scroll und flieg durch die Welt, in der er arbeitet.',
        tags: ['100 % lokal', 'Autonom', 'Enterprise']
      },
      {
        id: 'schreibtisch', label: 'Dein Schreibtisch', accent: '#d94f2b',
        still: '/assets/world/scene2.webp',
        clip: '/assets/world/dive2.mp4', clipMobile: '/assets/world/dive2-m.mp4',
        eyebrow: 'Einführung',
        title: 'Er zieht dort ein, wo du schon arbeitest.',
        body: 'Installiert auf deiner eigenen Infrastruktur — deine Desktops, deine Server, deine Apps. Kein SaaS-Mandant, keine Datenleitung in eine fremde Cloud.',
        tags: ['Deine Hardware', 'Deine Apps']
      },
      {
        id: 'team', label: 'Das Team', accent: '#d94f2b',
        still: '/assets/world/scene3.webp',
        clip: '/assets/world/dive3.mp4', clipMobile: '/assets/world/dive3-m.mp4',
        eyebrow: 'Das Team',
        title: 'Sechs Automation Systems. Eine Plattform.',
        body: 'Marketing · Research · Sales · Executive Assistant · YouTube · Customer Support — jedes ein konfigurierbarer KI-Mitarbeiter, der die Routinearbeit einer Abteilung übernimmt.',
        tags: ['Marketing', 'Research', 'Sales', 'Exec Assistant', 'YouTube', 'Support']
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
          secondary: { label: 'Sieh ihn arbeiten', href: YT, blank: true }
        }
      }
    ],
    connectors: ['/assets/world/conn12.mp4', '/assets/world/conn23.mp4', '/assets/world/conn34.mp4'],
    connectorsMobile: ['/assets/world/conn12-m.mp4', '/assets/world/conn23-m.mp4', '/assets/world/conn34-m.mp4']
  });
})();
