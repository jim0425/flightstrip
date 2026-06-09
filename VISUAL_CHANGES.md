# FlightStrip — Visual Restyle + Ad Slots + SEO/AI-Search (Format-Only Change)

**Date:** 2026-06-09
**Scope:** First (pre-generation) screen of the live frontend only. **No functionality changed.**
**Repo:** `jim0425/flightstrip` — applied in your canonical working copy `C:\Users\jimka\test-site\flightstrip\` (the one your pipeline deploys from; base commit `e1f800b` = live tag `v4`)
**Live frontend:** Vercel, served from `frontend/` (root rewrite → `index.html`)
**Live backend:** FastAPI on Render (`flightstrip-api.onrender.com`) — **untouched**

---

## Files changed

| File | Change |
|---|---|
| `frontend/index.html` | **Modified** — `<head>` SEO/OG/Twitter/JSON-LD, hero treatment, restyled control card, 3 ad slots, About + FAQ sections, print-safety CSS. |
| `frontend/assets/hero-n2552x.webp` | **New** — optimized hero photo of **your Cessna 206 (N2552X)** in a mountain meadow at golden hour (1920px, WebP q82, ~193 KB). |
| `frontend/assets/hero-n2552x.png` | **New** — full-res PNG fallback (3168×1344). |
| `frontend/robots.txt` | **New** — allows GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot + sitemap. |
| `frontend/sitemap.xml` | **New** — homepage. |
| `frontend/llms.txt` | **New** — plain-text tool description for AI assistants. |
| `frontend/og-image.png` | **New** — 1200×630 social/OG card (self-hosted). |
| `frontend/favicon.png` | **New** — 32×32 favicon. |
| `frontend/apple-touch-icon.png` | **New** — 180×180. |
| `scripts/make_og_assets.py` | **New** — Python/Pillow generator for the og-image + icons. |

## Files explicitly NOT touched (verified via `git status` + diff)

- **All of `backend/`** — route generation (`route.py`), weather/AVWX (`weather.py`), PDF/kneeboard (`templates/kneeboard.html`, `main.py`), staleness, affiliates, tests.
- No logic in `frontend/index.html`: every React state hook, handler (`generateRoute`, `downloadPdf`, `buildBody`), and child component (`WaypointInputs`, `RouteTable`, `AirportRow`, `DetailRow`, `FreqChip`, `WxBadge`) is **byte-for-byte unchanged**. Only the `<head>`, the `<style>` print block, a new `AdSlot` presentational component, and the JSX *layout/markup* of `App()`'s return were edited.

---

## What changed visually (first screen only)

1. **Aviation hero** behind the header — **your Cessna 206 (N2552X)** photo in a mountain meadow at
   golden hour, applied as the hero `<section>` CSS background (`/assets/hero-n2552x.webp`, PNG fallback
   via `image-set`), `center right / cover`. Because the aircraft sits right and the sky is open on the
   left, a **left-weighted** dark gradient (`90deg` 0.85→0.45→0 at 0/38/70%) keeps the headline + subtext
   legible. `bg-slate-900` is the base fallback color. Same-origin. Class `hero` (hidden in print).
2. **Modernized control card** — larger padding, softer shadow + ring/border, rounded corners,
   blue (`#1040bb`-family) accents on the slider/checkboxes. Same inputs, same buttons, same handlers.
3. **SEO hero subhead** added under the title (your words: "Stop pressing buttons…").
4. **Responsive 2-column layout** on `lg+` — tool + content left (max ~720px), sticky ad rail right;
   single-column on mobile.
5. **About / How it works** + **Who it's for** copy (your founder rationale voice).
6. **FAQ** (6 Q&As) that mirrors the FAQPage JSON-LD.

## Affiliate ad slots (empty placeholders — paste code later)

All carry `class="no-print ad-slot"`, a real HTML-comment marker in the DOM, a faint dashed "Ad"
placeholder, and are **never** mounted inside the results/kneeboard subtree (verified at runtime).

| Slot | Size | Placement | Marker |
|---|---|---|---|
| Leaderboard | 728×90 (→320×50 mobile) | directly below control card | `<!-- AFFILIATE AD SLOT [leaderboard][728x90]: … -->` |
| Skyscraper | 300×600 | right rail, `lg+` only, sticky | `<!-- AFFILIATE AD SLOT [right-rail-skyscraper][300x600]: … -->` |
| Medium rectangle | 300×250 | inside the About section | `<!-- AFFILIATE AD SLOT [in-content-rectangle][300x250]: … -->` |

**Ads stay visible on the route view:** results render in the left column, so the **leaderboard sits directly above the results** and the **300×600 skyscraper is sticky in the right rail** — both remain on screen while you read the generated route on desktop. On mobile the leaderboard sits above the results and the rectangle below, bracketing them. No ad is ever inside the results/kneeboard subtree, and all ads are hidden in the printed PDF.

To activate a slot, replace the `<AdSlot .../>` (or its inner placeholder) with your banner/affiliate code.

## SEO / AI-search

- `<title>` (98 chars), meta description (153 chars), canonical, theme-color, `robots: index,follow`.
- Open Graph + Twitter `summary_large_image` → `/og-image.png` (1200×630).
- Real semantic `h1` ("✈ FlightStrip / Free Pilot Kneeboard Generator"), `h2` (How it works · Who it's for · FAQ), 6 `h3` FAQ questions — clean h1→h2→h3 outline.
- JSON-LD: **SoftwareApplication** (free, UtilitiesApplication, Web), **Organization** (Bolder Aviation), **FAQPage** — all valid JSON.
- `/robots.txt`, `/sitemap.xml`, `/llms.txt` served at root by Vercel (filesystem wins over the catch-all rewrite).
- favicon + apple-touch-icon, `lang="en"`, viewport (pre-existing).

## Print safety

`@media print { .ad-slot, .hero, .site-about, .site-faq { display:none !important; } }` added,
on top of the existing `.no-print` rule (which also hides all of these). The printed kneeboard is unchanged.
The **PDF is generated server-side** by the FastAPI backend, so the hero/ads physically cannot appear in it.

---

## Verification performed (automated, in a headless browser against the live API)

- Page renders with **no console errors** (only the pre-existing Tailwind-CDN / in-browser-Babel warnings).
- Defaults intact: waypoints `KBJC` → `KSUN`, corridor slider `min 5 / max 50 / value 25`, `Public use only` ✓, `Exclude heliports` ✓, `Min runway 0`.
- Buttons intact: **Generate Route**, **⬇ Kneeboard PDF**. Footer text intact.
- Real route generation (KBJC→KSUN) returned **34 airports**; `RouteTable` rendered all 34 rows with the **same 10 columns**; PDF button enabled. **No ad slot inside the table / results.**
- `<head>` contains title, meta description, canonical, OG, Twitter, and 3 valid JSON-LD blocks.
- `robots.txt`, `sitemap.xml`, `llms.txt`, `og-image.png`, `favicon.png`, `apple-touch-icon.png` all present.
- Print rule + `no-print`/`ad-slot`/`hero`/`site-about`/`site-faq` classes confirmed on every marketing element.

## Deploy (your existing pipeline)

```
cd C:\Users\jimka\test-site\flightstrip
git add frontend/index.html frontend/assets/hero-n2552x.webp frontend/assets/hero-n2552x.png frontend/robots.txt frontend/sitemap.xml frontend/llms.txt frontend/og-image.png frontend/favicon.png frontend/apple-touch-icon.png scripts/make_og_assets.py VISUAL_CHANGES.md
git commit -m "Restyle first screen + N2552X hero + ad slots + SEO/AI-search (format only)"
git push          # Vercel auto-deploys frontend/ ; backend on Render is untouched
```
(Backend deploy is unaffected — nothing in `backend/` changed.)

To regenerate the og-image/icons: `python scripts/make_og_assets.py`
