# OrphicOS landing page

Static site, currently three design variants under review: `a/` (Museum plate), `b/` (Terminal heritage), `c/` (Type only) — each self-contained (`index.html` + `styles.css`) over shared `assets/`. The root `index.html` is an internal review page linking the three; replace it with the winning variant's page (fixing the `../assets` and `../download` paths) before deployment. No build step, no JS, no external requests (system fonts only). Design rationale in `design-research.md`.

## Deploy

Copy the `landing/` directory contents to any static web root, e.g. nginx:

```nginx
server {
    server_name orphicos.app;
    root /var/www/orphicos-landing;
    index index.html;
}
```

The download button links to `download/OrphicOS-Setup.exe` (relative). Place the installer at `<web root>/download/OrphicOS-Setup.exe` when it ships.

## Assets

- `assets/src/hero-banner.png` — original artwork (source of truth; not referenced by the page).
- `assets/hero-banner.webp` / `.jpg` — optimized hero (served).
- `assets/wave-strip.*`, `assets/storm-dim.*`, `assets/ship-mark.*` — texture/detail crops derived from the original.

Design tokens (colors) in each variant's `styles.css` are pixel-sampled from the hero artwork; provenance is commented inline. Artwork provenance is recorded in `THIRD-PARTY-NOTICES.txt` at the repo root.
