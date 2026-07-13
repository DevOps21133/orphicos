/* Hero flight config (EN) — mounts the scroll-world engine on #world. */
(function () {
  var el = document.getElementById('world');
  if (!el || !window.mountScrollWorld) return;
  var YT = 'https://www.youtube.com/channel/UCAZ4UmGpCjGsuipjz5-AdOQ';
  mountScrollWorld(el, {
    hint: 'scroll to fly in',
    diveScroll: 1.3,
    connScroll: 0.9,
    sections: [
      {
        id: 'machines', label: 'The machines', accent: '#d94f2b',
        still: '/assets/world/scene1.webp',
        clip: '/assets/world/dive1.mp4', clipMobile: '/assets/world/dive1-m.mp4',
        scroll: 1.6, linger: 0.35,
        eyebrow: 'OrphicOS · Enterprise Autonomous AI Employees',
        title: 'An AI employee that does the work — on your machines, not the cloud.',
        body: 'OrphicOS runs real business workflows end-to-end in your own apps. Scroll to fly through the world it works in.',
        tags: ['100% local', 'Autonomous', 'Enterprise']
      },
      {
        id: 'desk', label: 'Your desk', accent: '#d94f2b',
        still: '/assets/world/scene2.webp',
        clip: '/assets/world/dive2.mp4', clipMobile: '/assets/world/dive2-m.mp4',
        eyebrow: 'Deployment',
        title: 'It moves in where you already work.',
        body: 'Deployed on your own infrastructure — your desktops, your servers, your apps. No SaaS tenant, no data pipeline to somebody else’s cloud.',
        tags: ['Your hardware', 'Your apps']
      },
      {
        id: 'team', label: 'The team', accent: '#d94f2b',
        still: '/assets/world/scene3.webp',
        clip: '/assets/world/dive3.mp4', clipMobile: '/assets/world/dive3-m.mp4',
        eyebrow: 'The team',
        title: 'Six automation systems. One platform.',
        body: 'Marketing · Research · Sales · Executive Assistant · YouTube · Customer Support — each one a configurable AI employee doing a department’s repetitive work.',
        tags: ['Marketing', 'Research', 'Sales', 'Exec Assistant', 'YouTube', 'Support']
      },
      {
        id: 'guarantee', label: 'The guarantee', accent: '#d94f2b',
        still: '/assets/world/scene4.webp',
        clip: '/assets/world/dive4.mp4', clipMobile: '/assets/world/dive4-m.mp4',
        scroll: 1.7, linger: 0.4,
        eyebrow: 'The guarantee',
        title: 'Nothing ever leaves the building.',
        body: 'Your contracts, client data and source code stay on your drive. Capability and confidentiality — no trade-off.',
        cta: {
          primary: { label: 'Book an Enterprise Consultation', href: 'https://t.me/OrphicOS' },
          secondary: { label: 'Watch it work', href: YT, blank: true }
        }
      }
    ],
    connectors: ['/assets/world/conn12.mp4', '/assets/world/conn23.mp4', '/assets/world/conn34.mp4'],
    connectorsMobile: ['/assets/world/conn12-m.mp4', '/assets/world/conn23-m.mp4', '/assets/world/conn34-m.mp4']
  });
})();
