# iFilm Customer UI V2 — Design Specification (G0)

**Status:** Design only — not production implementation  
**Baseline:** production `v1.14.3` (`f6fb581`)  
**Brand:** iFilm · company attribution **iFilm by Haroon Net**  
**Trains:** G0 (this doc) → G1 → G2 → G3 (separate PRs, human visual approval between trains)  
**Prototypes:** [`docs/design/prototypes/`](./prototypes/)  
**Screenshots:** [`docs/design/screenshots/`](./screenshots/) · artifacts `/opt/cursor/artifacts/customer-ui-v2-g0/`  
**G0 review report:** [`docs/design/G0_REVIEW.md`](./G0_REVIEW.md)

---

## 0. Purpose & constraints

This document defines the **customer** visual system before any production UI rewrite.

| Do | Do not |
|---|---|
| Feel like a premium modern streaming product | Feel like a React CMS / Bootstrap admin |
| Use real catalog APIs / artwork | Invent fake titles or fake track availability |
| Preserve v1.12+/v1.14 performance architecture | Preload every hero/carousel image |
| Manual hero navigation only | Auto-rotate hero / timer restart |
| Tasteful gold accents | Yellow-dominant UI |
| Replace customer-facing Mobin Net → Haroon Net | Blindly rename internal tech identifiers |
| Geometry-matched skeletons | Empty black loading screens |
| Intentional RTL per component (FA/PS) | One global mirror transform |

**Reference recording:** visual & interaction benchmark only. Do not copy branding, logos, artwork, source, or exact CSS.

**Admin vs customer:** may share primitives/tokens; must not look like the same product.

---

## 1. Design principles

1. **Cinematic density** — content fills the frame; posters large; hero dominant.
2. **Hierarchy** — brand → hero title → primary CTA → shelves; one job per section.
3. **Dark atmosphere** — deep navy/charcoal surfaces; gold used sparingly.
4. **Content-first** — artwork and titles carry the page; chrome stays quiet.
5. **Spacious, not sparse** — avoid tiny cards *and* giant empty gutters.
6. **Motion with purpose** — 150–300ms opacity/transform; respect `prefers-reduced-motion`.
7. **Truthful UI** — audio/subtitle badges only from media-track / catalog metadata.
8. **Keyboard & future-TV ready** — visible focus; no hover-only architecture.
9. **Locale-native** — EN LTR; FA/PS RTL layout with LTR player.
10. **Performance-preserving** — aggregated home, responsive images, lazy routes.

---

## 2. Typography

| Role | Font | Weight | Size (desktop) | Notes |
|---|---|---|---|---|
| Brand wordmark | Existing iFilm logo treatment | — | ~28–36px height | Distinctive; not body type |
| Hero title | `Fraunces` (display) | 700 | clamp(2.5rem, 5vw, 4.5rem) | Or title logo when available |
| Section title | `Fraunces` | 600–700 | 1.35–1.75rem | Shelf / detail section heads |
| Card title | `Outfit` | 600 | 0.875–1rem | 2-line clamp |
| Body / overview | `Outfit` | 400 | 1–1.125rem | Max measure ~42rem |
| Metadata | `Outfit` | 500 | 0.8125–0.875rem | Year · runtime · rating |
| UI chrome | `Outfit` | 500–600 | 0.875rem | Nav, buttons, filters |

**Avoid:** 11px metadata everywhere; mismatched giant serifs on every heading; too many weights (>4).

**RTL typography:** FA/PS use same stacks with `dir="rtl"`; overview measure still ~42rem; PS catalog text follows existing rule — **English fallback, never Persian fallback**.

---

## 3. Color & surface system

Customer dark theme (CSS variables — conceptual tokens for V2):

| Token | Approx | Use |
|---|---|---|
| `--bg-base` | `#0B0F17` / `hsl(222 28% 7%)` | Page background |
| `--bg-elevated` | `#121826` | Panels, scrolled header |
| `--bg-surface` | `#1A2233` | Controls, filter chips |
| `--bg-hover` | `#243044` | Hover fills |
| `--text-primary` | `#F2F5FA` | Titles |
| `--text-secondary` | `#A8B0C0` | Meta / overview |
| `--text-muted` | `#7A8499` | Secondary labels |
| `--gold` | `hsl(38 94% 55%)` | Logo, CTA, active, focus ring |
| `--gold-soft` | gold @ 15–25% | Selected chip wash |
| `--danger` | `#E5484D` | Errors |
| `--success` | `#3D9A6A` | Success toasts |
| `--border-subtle` | white @ 8–12% | Control borders |
| `--scrim` | black @ 40–70% | Hero overlays |

**Gold budget:** logo, primary Play, active nav/tab, focus ring, progress fill, selected filter. Not backgrounds, not large fills.

**Surface levels**

| Level | Treatment |
|---|---|
| L0 Base | solid `--bg-base` |
| L1 Elevated | `--bg-elevated` + optional blur |
| L2 Control | `--bg-surface` + 1px subtle border |
| L3 Overlay | glass `bg/55` + `backdrop-blur` |
| Hero media | full-bleed image + gradient scrims |

---

## 4. Spacing

Scale (4px base): `4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64 · 80 · 96`

| Context | Token |
|---|---|
| Page edge (desktop) | 48–64px (`--page-gutter-lg`) |
| Page edge (mobile) | 16–20px (`--page-gutter-sm`) |
| Shelf gap (title → rail) | 16–20px |
| Card gap in rail | 12–16px |
| Section vertical | 40–56px |
| Overview max width | 42rem |
| Content max (browse grids) | 90rem / 1440–1600px usable |

---

## 5. Card dimensions

| Property | Value |
|---|---|
| Aspect | **2:3** poster |
| Desktop width | **190–230px** (`posterSm` 190 → `posterLg` 230) |
| Tablet | ~168–190px |
| Mobile | ~156–168px (≈2.2–2.4 visible) |
| Radius | 12px (`--radius-card`) |
| Shadow rest | soft elevation |
| Shadow hover | deeper + slight lift |
| Episode cards | **landscape 16:9**, width ~280–340px — never poster-shaped |

**Card content:** artwork · title · optional year · rating when useful · ≤1–2 badges (dub/sub) · progress for Continue Watching.

---

## 6. Hero dimensions

| Viewport | Height |
|---|---|
| Desktop ≥1280 | **75–85vh** (cap ~900px) |
| Laptop 1024–1280 | **70–80vh** |
| Tablet | **55–65vh** |
| Mobile | **58–68vh** (crop tighter; shorter overview) |

**Composition**

- Full-bleed backdrop (edge-to-edge).
- Content column: start-aligned in LTR, end-aligned in RTL (logical `inline-start`).
- Gradients: horizontal scrim behind copy; bottom fade into `--bg-base`; light vignette.
- Overlay: title/logo · short overview (2–3 lines desktop, 1–2 mobile) · year · rating · runtime · genres · dub/lang chips.
- Actions: **Play** (primary) · **More Info** · optional **My List**.
- Controls: prev/next + dots (desktop); swipe + dots (mobile).

**Manual only — no autoplay timer.**

---

## 7. Gradients

| Name | Spec |
|---|---|
| Hero side | `linear-gradient(to inline-end, hsl(222 28% 7% / 0.92) 0%, hsl(222 28% 7% / 0.55) 45%, transparent 70%)` |
| Hero bottom | `linear-gradient(to top, var(--bg-base) 0%, transparent 55%)` |
| Header top | `linear-gradient(to bottom, hsl(0 0% 0% / 0.65), transparent)` when over hero |
| Card overlay | `linear-gradient(to top, hsl(0 0% 0% / 0.85), transparent 60%)` on hover |
| Vignette | radial soft edge darken ≤25% opacity |

---

## 8. Buttons

| Variant | Height | Style |
|---|---|---|
| Primary (Play) | 44–48px | Solid gold, dark text, radius 10px |
| Secondary (More Info) | 44–48px | Translucent white/12, border white/20 |
| Ghost / icon | 40–44px | Transparent, icon 20–22px |
| Filter chip | 36–40px | Surface L2, gold wash when active |
| Text | radius 10–12px; min tap 44×44 |

Icon + label on primary/secondary; icon-only allowed in header with `aria-label`.

---

## 9. Icons

| Size | Use |
|---|---|
| 18px | Inline meta |
| 20–22px | Header / bottom nav |
| 24px | Hero controls, card hover actions |
| Stroke | 1.75–2px, rounded caps |
| Library | Prefer existing Lucide (or current icon set) — no new heavy icon packs |

---

## 10. Navigation

### Desktop header

- Over hero: transparent + top gradient; height **64–72px**.
- After scroll (≥24px): solid/semi `--bg-elevated` @ ~85% + `backdrop-blur` 12–16px.
- **Start:** iFilm logo.
- **Center / mid:** Home · Movies · Series · Children · Genres · More.
- **End:** Search · Language · Notifications (if used) · Profile.
- Compact — not a tall marketing bar.

### Mobile bottom nav

| Tab | Route idea |
|---|---|
| Home | `/` |
| Movies | `/movies` |
| Series | `/series` |
| Search | `/search` |
| Profile | `/profile` or login |

- `padding-bottom: env(safe-area-inset-bottom)`.
- Active = gold icon/label.
- Request Movie is **not** a permanent tab.
- Content must clear bottom nav (extra bottom padding on pages).

---

## 11. Responsive breakpoints

| Name | Min width | Notes |
|---|---|---|
| `xs` | 0 | Mobile-first |
| `sm` | 480 | Larger phones |
| `md` | 768 | Tablet / bottom nav → desktop header transition zone |
| `lg` | 1024 | Desktop nav solid |
| `xl` | 1280 | Full cinematic hero |
| `2xl` | 1536 | Max content width comfort |

**QA matrix:** 1920×1080 · 1600×900 · 1440×900 · 1366×768 · 1024×768 · 768×1024 · 430×932 · 390×844 × EN/FA/PS.

---

## 12. RTL behavior

| Surface | Behavior |
|---|---|
| Page shell (FA/PS) | `dir="rtl"` `lang="fa"|"ps"` |
| Player | **Always `dir="ltr"`** |
| Header | Logo at inline-start; actions at inline-end; menu order designed (not accidental mirror) |
| Hero copy | Align to inline-start; side gradient flips with logical directions |
| Carousel arrows | “Previous” scrolls toward inline-end content start; icons match mental model — verify with mouse/touch/keyboard |
| Filters / dropdowns | Panel opens toward inline-start; checkmarks on correct side |
| Search expand | Grows toward inline-start |
| Episode rows | Thumbnail inline-start → meta → play |
| Progress bars | Fill from inline-start |
| Bottom nav | Same tab set; icon order designed for RTL |

**PS metadata:** English fallback when PS missing; never substitute Persian.

---

## 13. Animation rules

| Interaction | Motion |
|---|---|
| Hero slide change | Backdrop crossfade 280–400ms + content fade; optional subtle 12–20px translate |
| Card hover | scale 1.04–1.06, lift 4–8px, overlay fade — **grid must not reflow** |
| Header scroll | background/blur 200ms |
| Shelf scroll | CSS scroll-behavior smooth (user) |
| Dropdown / sheet | 180–240ms opacity + translate |
| Detail trailer reveal | After ~6s backdrop, crossfade to muted trailer — no layout jump |

**Forbidden:** bounce, spin, excessive zoom, autoplay trailers on every card hover, shelf auto-scroll, hero timer.

**`prefers-reduced-motion: reduce`:** opacity-only or instant; no translate/scale.

---

## 14. Loading states

Geometry-matched skeletons (shimmer on L1/L2 surfaces):

| Page | Skeletons |
|---|---|
| Home | Hero block + 2–3 row rails |
| Browse | Poster grid |
| Detail | Hero + meta lines + cast circles/rects + rail |
| Search | Compact poster grid |

Never leave a blank black viewport.

---

## 15. Accessibility

- Visible focus ring: 2px gold (or high-contrast) offset.
- All icon buttons: `aria-label` (localized).
- Carousel: prev/next buttons, dots with `aria-current`, keyboard operable.
- Cards: focusable; Enter → detail; optional Space → play when authenticated policy allows.
- Contrast: body text ≥ 4.5:1 on dark surfaces; gold-on-dark CTAs verified.
- Reduced motion respected.
- Screen-reader: shelf labels, hero “slide x of n”, progress “x% watched”.

---

## 16. Desktop wireframes

### Home (1920 / 1440)

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo]  Home Movies Series Children Genres More    🔍 🌐 👤 │  ← transparent over hero
├─────────────────────────────────────────────────────────────┤
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ HERO ~80vh ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│  Title / Logo                                               │
│  overview…                                                  │
│  2026 · 8.1★ · 2h 18m · Sci-Fi                              │
│  [ Play ]  [ More Info ]  [ My List ]                       │
│                                         ‹  ● ○ ○  ›         │
├─────────────────────────────────────────────────────────────┤
│ Popular Now                                      See all ›  │
│ [card][card][card][card][card][card]…              ‹ ›      │
│ New Releases …                                              │
│ Top Rated …                                                 │
│ Genre shelves…                                              │
├─────────────────────────────────────────────────────────────┤
│ Footer: Discover · Company · Legal · iFilm by Haroon Net    │
└─────────────────────────────────────────────────────────────┘
```

Authenticated shelf order (skip empties): Continue Watching → My List → Recommended → Because You Watched → Featured Collections → New Releases → Popular → Dubbed → Subtitled → Genre shelves.

Anonymous: Featured → Popular Now → New Releases → Collections → Genres.

### Movie detail

```
┌─ full-bleed hero (backdrop → optional muted trailer @6s) ─┐
│ Title · meta · [Play][My List][Trailer]                     │
│ Audio / Subtitle chips (truthful)                           │
│ Overview (max ~42rem)                                       │
│ Cast carousel                                               │
│ More Like This / Similar (deduped labels)                   │
└─────────────────────────────────────────────────────────────┘
```

### Series detail

Same cinematic system + season selector + landscape episode cards (thumbnail, SxEx, title, duration, description, progress, Play/Resume).

### Browse /movies|/series

Title → premium filter row → responsive poster grid (shared `MediaCard`).

---

## 17. Mobile wireframes (390×844)

```
┌──────────────────────┐
│ Logo          🌐 👤  │
├──────────────────────┤
│ HERO ~62vh           │
│ Title                │
│ short overview       │
│ [ Play ] [ Info ]    │
│     ○ ● ○            │  swipe
├──────────────────────┤
│ Shelf title          │
│ [card][card][card→   │  snap scroll
│ …                    │
├──────────────────────┤
│ Home Movies Series   │
│ Search Profile       │  + safe-area
└──────────────────────┘
```

Detail mobile: backdrop → title → actions → meta → overview → cast → similar. No huge empty vertical voids.

Filter mobile: **Filter** button → bottom sheet (not 8 dropdowns in 390px).

Search mobile: full-screen search view.

---

## 18. Global design tokens (implementation checklist)

Reusable primitives (extend `design-system/tokens.ts` / CSS vars in G1):

```
CONTENT WIDTHS     --content-max, --overview-max (42rem), --page-gutter-*
SPACING SCALE      4–96 as above
CARD WIDTHS        156 / 168 / 190 / 210 / 220 / 230
CARD ASPECT        2/3 poster · 16/9 episode
HERO HEIGHTS       58–85vh by breakpoint
BORDER RADII       control 10 · card 12 · sheet 16 · pill avoid unless chip
SURFACE LEVELS     L0–L3
SHADOWS            rest / hover / modal
TYPOGRAPHY SCALE   display / section / card / body / meta
BUTTON HEIGHTS     36 / 40 / 44 / 48
ICON SIZES         18 / 20 / 22 / 24
Z-INDEX            base 0 · sticky header 40 · dropdown 50 · sheet 60 · player 100 · toast 110
BREAKPOINTS        xs–2xl
FOCUS              ring gold 2px offset 2
```

---

## 19. Feature specifications (summary)

### Hero (homepage)

- Manual prev/next + dots; mobile swipe; **no timer**.
- Priority-load **active** backdrop only (`w1280` desktop / `w780` mobile class equivalents on our artwork pipeline).
- Idle prefetch **next** slide only.
- Never `/original/` unnecessarily.
- Transitions: crossfade + light content fade; reduced-motion → cut/fade only.

### Media cards & hover

- Larger premium posters; hover overlay with Play / My List / Details + compact meta.
- **No grid jump**; **no trailer autoplay on hover**.
- Focus ring + Enter opens detail.

### Continue Watching

- Progress bar on card bottom; optional time remaining; resume on Play.
- Episodes: Series title + `S1 · E3`.

### Browse & filters

- Shared cards for movies/series.
- Dark premium controls; active gold wash; RTL-aware menus.
- Mobile filter sheet.

### Detail V2

- Cinematic hero; truthful audio/subtitle lines from media tracks.
- 6s backdrop → muted trailer if present (existing behavior preserved).
- Cast carousel (portrait · name · character); crew limited to Director / Writer / Creator.
- Recs: dedupe rows; use existing recommendation system when non-empty.

### Player

- No playback-architecture redesign in GUI trains.
- Launch/overlay visual polish only; player always LTR.

### Search / What to Watch / Request / Profile

- Premium visual layer on existing functionality; empty states friendly; no raw API errors.
- Request: centered panel, less “enterprise form”; signed-out without huge empty space.
- What to Watch: large chips/steps, not survey forms.

### Footer

- Brand: iFilm · iFilm by Haroon Net.
- Remove prominent customer-facing Mobin Net attribution where product branding requires.
- Sections: Discover · Company · Legal.
- TMDB: move to discreet Credits/About/Legal page with accurate non-endorsement wording — do not falsely imply endorsement.

### Image fallbacks

- Poster / backdrop / cast missing → branded placeholder (gradient + title initials), never broken-image icon.

### Error states

- Content/playback/entitlement/empty watchlist/CW/recs/API failure — human copy only.

### Performance & bundle

- Keep aggregated home APIs, lazy routes, gzip, image budgets.
- Do not import admin into customer entry; do not global-load player/trailer.
- Material JS growth must be measured and explained (G1+).

### TV foundations (not a TV app yet)

- Focusable cards, large targets, selected state — prepare remote navigation later.

---

## 20. Implementation order

| Train | Scope | Gate |
|---|---|---|
| **G0** | This spec + prototypes + screenshots | Human visual review |
| **G1** | Tokens, header, homepage hero, shelves, MediaCard | Prod verify + screenshots |
| **G2** | Movie/Series detail, cast, episodes | Prod verify + screenshots |
| **G3** | Browse, filters, search chrome, footer, request, mobile polish | Prod verify + screenshots |

Do not run G1/G2/G3 in one PR. Do not start T1 DB work in this train.

Where UI needs future T2/T4/T5 data: design now; bind to truthful current APIs until those trains land.

---

## 21. Screenshot / Ready gate

GUI PR is **not** Ready from pytest/vitest/build alone. Required screenshots (minimum):

| Locale | Desktop | Mobile |
|---|---|---|
| EN | Home, Movies, Movie Detail, Series Detail | Home, Movie Detail, Search |
| FA | Home, Movie Detail | Home, Movie Detail, footer/bottom nav |
| PS | — | Home, Movie Detail |

Changed surfaces: BEFORE/AFTER + short note (what/why/responsive/RTL/perf).

G0 provides **design prototypes** (not production before/after) using live catalog data.

---

## 22. Unresolved design decisions (need PO input)

1. **Children** nav destination — dedicated kids hub vs filtered browse?
2. **More** menu contents — exact links (Collections, What to Watch, Request, Help…)?
3. **Notifications** — ship icon in G1 or hide until backend exists?
4. **Title logos** in hero — prefer logo_url over text when present?
5. **My List** on hero for anonymous — hide vs prompt sign-in?
6. **TMDB Credits page** — new route `/credits` vs section on About?
7. **Haroon Net** legal URLs (contact, privacy support) — final copy/links?
8. **Series Detail** season control — dropdown vs segmented for >5 seasons?
9. **Continue Watching** row for anonymous — always hide?
10. **Gold intensity** — confirm against prototypes (Soulm8te / Interstellar frames).

---

## 23. Prototype index

| File | Description |
|---|---|
| [`prototypes/home.html`](./prototypes/home.html) | Homepage — `?locale=en\|fa\|ps` |
| [`prototypes/detail.html`](./prototypes/detail.html) | Movie detail (Interstellar #14) — same locale query |
| [`prototypes/catalog-data.json`](./prototypes/catalog-data.json) | Slim snapshot from production APIs |
| [`prototypes/prototype.css`](./prototypes/prototype.css) | V2 token & layout CSS for mocks only |
| [`screenshots/`](./screenshots/) | Captured frames for review |

**Data note:** `moreLikeThis` on detail prototypes uses real titles from home shelves when the similar endpoint is empty — layout demonstration only; production will use recommendation/similar payloads when present and omit empty shelves.
