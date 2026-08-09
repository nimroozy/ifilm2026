# G1 Report — Customer UI V2 Foundation & Homepage

**Status:** Ready for human visual approval (do not merge automatically)  
**PR:** [#69](https://github.com/nimroozy/ifilm2026/pull/69)
**Head SHA:** `e33ac108c0ece38f28b2c79bee3e4010c21a51a0`  
**Branch:** `cursor/customer-ui-v2-g1-homepage-4873`  
**Baseline:** production `v1.14.3`  
**Scope:** G1 only — no G2 detail, G3 polish, T1 backend

---

## Changed customer components

| Area | Files |
|---|---|
| Tokens | `design-system/tokens.ts`, `design-system/index.ts` |
| Header / shell | `CustomerLayout.tsx`, `DesktopNav.tsx`, `navConfig.ts` |
| Hero | `HeroCarousel.tsx` |
| Cards / shelves | `MediaCard.tsx`, `ContentShelf.tsx`, `SectionHeader.tsx` |
| Home | `Index.tsx` |
| Footer / Credits | `CustomerFooter.tsx`, `LegalPages.tsx` |
| Tests | `heroCarousel.test.tsx`, `customerChrome.test.tsx`, `navConfig.test.ts`, `designSystem.test.tsx`, `playwright.phase3.spec.ts` |

---

## Design tokens

Implemented shared primitives: surfaces, typography, spacing, radii, hero sizing, media card widths (190–230px), z-index, button/icon sizes, motion. Gold reserved for logo, primary CTA, active nav, selected controls, focus/progress accents.

---

## Hero

- Cinematic full-bleed (~62vh mobile / ~78–82vh desktop)
- Side + bottom scrims, vignette
- Title logo when `logoUrl` present; else styled text
- Meta: year · rating · runtime · genres
- Actions: Play · More Info · My List (auth → watchlist API; anon → `/login`)
- **Manual only:** `data-autoplay="false"` — no timer / auto-advance
- Prev/next + dots; swipe; keyboard arrows (RTL-aware)
- Perf: active LCP preload only; idle prefetch next; `heroBackdropSrcSet` (w780/w1280)

---

## MediaCard V2

- Poster density tokens unchanged/premium
- Hover/focus overlay: Play / My List / Details + compact meta
- Scale/lift on poster only (no grid reflow)
- No trailer autoplay
- Progress bar for Continue Watching
- Episode context via `status` (`S1 · E3`)

---

## Shelves / carousels

- Manual horizontal rails; snap on mobile; hidden scrollbar
- RTL-aware prev/next via document `dir`
- Empty shelves still omitted
- Auth CW / My List remain authenticated-only

---

## Mobile navigation

- Tabs: Home · Movies · Series · Search · Profile
- Safe-area padding; content/footer clearance
- Active gold state; Request Movie not a tab
- Notifications icon removed (no dead control)

---

## More menu

Always: Collections · What to Watch · Dubbed · Subtitled · New Releases · Request Movie  
Primary: Home · Movies · Series · Children · Genres

---

## RTL

Verified FA/PS: header, hero, metadata, CTAs, shelves, language control, bottom nav. Player untouched (still LTR).

---

## Accessibility

- Focus rings on cards/controls
- Hero carousel aria roles/labels; keyboard arrows
- Card Enter/Space + overlay buttons
- `prefers-reduced-motion` respected (hero fade / CSS global)

---

## Performance before/after

| Metric | After (local production build) | Notes |
|---|---|---|
| Customer entry JS (`index-*.js` main) | ~308 KB raw · ~99.6 KB gzip | No new UI libraries |
| Homepage API | Still aggregated `catalog/home` / `me/home` | No fan-out reintroduced |
| Hero images | Active only + idle next | Unchanged strategy |
| Player chunk | Separate lazy `PlayerPage` | Not in customer entry |

Homepage SQL / LCP field numbers require production deploy measurement — architecture unchanged from v1.14.3.

---

## Browser QA (G1 surfaces)

Captured: 1440×900 EN/FA, 390×844 EN/FA/PS. Additional viewports (1920, 1600, 1366, 1024, 768, 430) should be spot-checked in review.

---

## Screenshots

| | Path |
|---|---|
| Artifacts | `/opt/cursor/artifacts/customer-ui-v2-g1/{before,after}/` |
| Repo | `docs/design/screenshots/g1/{before,after}/` |

Required: Desktop EN before/after · Desktop FA after · Mobile EN before/after · Mobile FA/PS after.

---

## Remaining visual findings

1. Mobile hero stacks three CTAs — dense on 390px; acceptable for G1, polish in G3 if needed.
2. Footer tagline still mentions Mobin Net (branding copy deferred; TMDB removed from footer → Credits).
3. Anonymous My List is visible and routes to sign-in (per PO).

---

## Deviations

- Did not redesign Movie/Series detail (G2).
- Did not redesign browse/search/filters (G3).
- Kids profiles not implemented — `/children` curated route retained.
- Season selector N/A in G1.
