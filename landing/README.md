# OrphicOS landing page

Static site selling **OrphicOS — Enterprise Autonomous AI Employees**: an autonomous agent
that runs real business workflows end to end in a company's own desktop apps, **locally, on
their own infrastructure** ("nothing leaves the building"). Positioning is grounded in the
product's own strategy docs (`E:\youtube raw ai\ROADMAP.md`, `PRODUCT-ANGLE.md`,
`CONTENT-PATH-MUST-FULFILL.md`, `ENTERPRISE-MISSION-REPORT-FRAMEWORK.md`).

- `index.html` — English landing page. Links `styles.css` + `assets/fonts/fonts.css`.
- `de/index.html` — German mirror (same stylesheet, same fonts).
- `styles.css` — the whole design system: dark, technical, premium (the OpenAI/Vercel/
  Linear/Stripe register). Fraunces (display) + Inter (body) + IBM Plex Mono (the "AI-OS"
  layer). Strict 8px rhythm, one rationed accent + a "local/secure" signal green.
- Fonts are self-hosted under `assets/fonts/` → **zero external requests**. A tiny inline
  script does nav-hairline + reveal-on-scroll only; the page is fully readable with JS off.

The primary CTA everywhere is **Book an Enterprise Consultation** — a link to Telegram
`t.me/OrphicOS`, never a checkout or a "Subscribe". The secondary CTA links to the
YouTube Mission Logs (EN channel / `@the-raw-ai` on the DE page).

The prior "voice desktop helper / museum-plate" design is retired. The unchosen variants
(`b/` Terminal heritage, `c/` Type only) and the maritime hero artwork under `assets/` stay
in the repo as history; they are no longer referenced by the page. Design rationale for the
restrained-site research is still in `design-research.md`.

## Deploy

Copy the `landing/` directory contents to any static web root, e.g. nginx:

```nginx
server {
    server_name orphicos.app;
    root /var/www/orphicos-landing;
    index index.html;
}
```

`/` serves the English page; `/de/` serves the German page. No build step, no external
requests.

## Assets

- `assets/favicon.ico` / `.png` — favicon (still used).
- `assets/fonts/` — self-hosted Fraunces / Inter / IBM Plex Mono (`fonts.css`).
- `assets/hero-banner.*`, `wave-strip.*`, `storm-dim.*`, `ship-mark.*`, `src/` — artwork from
  the retired design; kept for provenance, not referenced by the current page. Provenance is
  recorded in `THIRD-PARTY-NOTICES.txt` at the repo root.
