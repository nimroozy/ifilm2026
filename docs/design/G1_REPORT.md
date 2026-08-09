# G1 Report — Customer UI V2 Foundation & Homepage

**Status:** Ready for human visual approval (do not merge automatically)  
**PR:** [#69](https://github.com/nimroozy/ifilm2026/pull/69)  
**Head SHA:** see branch tip `cursor/customer-ui-v2-g1-homepage-4873`  
**Branch:** `cursor/customer-ui-v2-g1-homepage-4873`  
**Baseline:** production `v1.14.3`  
**Scope:** G1 only — no G2 detail, G3 polish, T1 backend

---

## Polish pass (post-draft review)

| Item | Result |
|---|---|
| Mobile CTA density | Fixed — single row `[Play] [More Info] [+]` at ≤md; desktop keeps full labels |
| Haroon Net branding | Customer-facing Mobin Net → **iFilm by Haroon Net** (footer, legal copy, login notes, meta). Support URLs unchanged (no invented Haroon URLs) |
| TMDB | Still Credits-only; no footer TMDB branding; `credits-tmdb` retained |
| Viewport matrix | **24/24 green** (8 viewports × EN/FA/PS) — see `docs/design/screenshots/g1/viewport-qa.json` |
| Hero manual | Confirmed `data-autoplay="false"`; no timer |
| Bundle | ~309.4 KB raw · ~100.1 KB gzip (≈stable vs prior ~308 / 99.6) |

---

## Changed customer components

| Area | Files |
|---|---|
| Tokens | `design-system/tokens.ts`, `design-system/index.ts` |
| Header / shell | `CustomerLayout.tsx`, `DesktopNav.tsx`, `navConfig.ts` |
| Hero | `HeroCarousel.tsx`, `WatchlistButton.tsx` (`iconOnly`) |
| Cards / shelves | `MediaCard.tsx`, `ContentShelf.tsx`, `SectionHeader.tsx` |
| Home | `Index.tsx` |
| Footer / branding | `CustomerFooter.tsx`, `translations.ts`, `index.html`, `LegalPages.tsx` |
| Tests | hero / chrome / nav / design system / admin meta / playwright.phase3 |

---

## Design tokens

Shared primitives: surfaces, typography, spacing, radii, hero sizing, card widths (190–230px), z-index, motion. Gold reserved for logo, primary CTA, active nav, selected controls, focus/progress.

---

## Hero

- Cinematic full-bleed; bottom-weighted content (not vertically centered)
- Side + bottom scrims + vignette
- Title logo when available; text fallback
- Mobile meta trimmed (1 genre chip); desktop shows more
- Actions: Play · More Info · My List (auth API / anon → `/login`)
- **Mobile CTA row:** Play + More Info + icon My List — no stacked third full button
- **Manual only** — prev/next/dots; swipe; keyboard; idle image prefetch only
- Arrow controls: compact, high-contrast (`bg-black/55`), focus ring, RTL chevron flip
- Dots subtle (`h-1.5`, short active pill)

---

## MediaCard V2

- 2:3 posters; premium density
- Hover/focus: Play / My List / Details + **one-line** compact meta (`line-clamp-1`)
- No layout reflow; no trailer autoplay
- CW: thin progress bar + `S·E` via `status`

---

## Mobile navigation

Home · Movies · Series · Search · Profile — safe-area, clearance verified in matrix (no footer/nav overlap).

---

## Footer

- Brand byline: **iFilm by Haroon Net**
- Mobile: accordion sections (Discover / Company / Legal) to avoid giant vertical wall
- Credits link; no TMDB in main footer

---

## Viewport matrix result

Viewports: 1920×1080, 1600×900, 1440×900, 1366×768, 1024×768, 768×1024, 430×932, 390×844  
Locales: EN / FA / PS  

Checked: overflow-x, title clip, CTA outside hero, bottom-nav/footer overlap, Mobin branding, autoplay flag, RTL dir.

**Failed: 0 / 24**

Artifact: `/opt/cursor/artifacts/customer-ui-v2-g1/viewport-qa.json`

---

## Performance

| Metric | Value |
|---|---|
| Main customer JS | ~309.4 KB raw · ~100.1 KB gzip |
| Home API | Aggregated `catalog/home` (unchanged) |
| Hero images | Active LCP + idle next only |
| New libraries | None |

---

## Screenshots

| Shot | Path |
|---|---|
| Desktop EN 1440 | `docs/design/screenshots/g1/after/home-desktop-en.png` |
| Desktop FA 1440 | `docs/design/screenshots/g1/after/home-desktop-fa.png` |
| Mobile EN 390 | `docs/design/screenshots/g1/after/home-mobile-en.png` |
| Mobile FA 390 | `docs/design/screenshots/g1/after/home-mobile-fa.png` |
| Mobile PS 390 | `docs/design/screenshots/g1/after/home-mobile-ps.png` |
| Mobile EN 430 | `docs/design/screenshots/g1/after/home-mobile-430-en.png` |
| Before (prod) | `docs/design/screenshots/g1/before/` |
| Artifacts | `/opt/cursor/artifacts/customer-ui-v2-g1/` |

---

## Ready gate checklist

- [x] Mobile CTA density fixed
- [x] Haroon Net customer branding fixed
- [x] Full viewport spot-check green
- [x] No hero clipping
- [x] No mobile nav overlap
- [x] No visual RTL dir problems in matrix
- [x] Manual hero still manual
- [x] Performance preserved
- [x] Targeted Vitest green
- [ ] Human visual approval (merge gate)
- [ ] CI green on PR

---

## Remaining findings (non-blocking)

1. Footer social hrefs still point at existing `mobinnet.af` URLs (intentional — no invented Haroon Net URLs).
2. Desktop hero renders both icon + labeled My List in DOM (CSS-hidden); acceptable, not customer-visible.
3. Full CI run should be confirmed on GitHub Actions after push.

**Do not auto-merge. STOP after G1 Ready — no G2 until human approval.**
