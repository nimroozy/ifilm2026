# G0 Review Report — Customer UI V2 Design

**Train:** G0 (design only)  
**Branch:** `cursor/customer-ui-v2-design-g0-4873`  
**Baseline:** production `v1.14.3` (`f6fb581`)  
**Status:** STOP — awaiting human visual approval before G1

---

## Deliverables

| Item | Path |
|---|---|
| Design specification | [`docs/design/CUSTOMER_UI_V2.md`](./CUSTOMER_UI_V2.md) |
| HTML prototypes | [`docs/design/prototypes/`](./prototypes/) |
| Catalog snapshot (live API) | [`docs/design/prototypes/catalog-data.json`](./prototypes/catalog-data.json) |
| Screenshots | [`docs/design/screenshots/`](./screenshots/) |
| Artifacts copy | `/opt/cursor/artifacts/customer-ui-v2-g0/` |

**Open prototypes locally**

```bash
cd docs/design/prototypes
python3 -m http.server 8765
# http://127.0.0.1:8765/home.html?locale=en
# http://127.0.0.1:8765/home.html?locale=fa
# http://127.0.0.1:8765/detail.html?locale=en
```

Optional offline artwork cache for captures: run prefetch (see `capture-screenshots.mjs` comments) → `catalog-data.local.json` + `assets/` (not committed).

---

## Design tokens (summary)

| Category | V2 direction |
|---|---|
| Surfaces | `--bg-base #0B0F17` · elevated `#121826` · control `#1A2233` |
| Accent | Gold `hsl(38 94% 55%)` — logo, Play, active, focus only |
| Type | Display `Fraunces` · UI/body `Outfit` |
| Cards | 190–230px desktop · **2:3** · radius 12 |
| Hero | 70–85vh desktop · 58–68vh mobile · full-bleed |
| Motion | 150–300ms · crossfade/fade/translate · `prefers-reduced-motion` |
| Brand | **iFilm** · **iFilm by Haroon Net** (replace customer-facing Mobin Net) |
| Z-index | header 40 · dropdown 50 · sheet 60 · player 100 |

Full token tables: §2–§11 and §18 in `CUSTOMER_UI_V2.md`.

---

## Hero specification

- Height ~75–85vh desktop / ~62vh mobile; edge-to-edge backdrop.
- Side + bottom scrims; vignette optional.
- Overlay: title, overview (clamped), year · rating · runtime · genres · dub chip.
- CTAs: Play · More Info · My List.
- **Manual navigation only** — prev/next + dots (desktop); swipe + dots (mobile).
- **No autoplay timer** (explicit product requirement vs current 8s autoplay).
- Perf: priority-load active artwork only; idle prefetch next; `w780` / `w1280` class equivalents; no `/original/`.

---

## Card specification

- Desktop width 190–230px; 2:3 poster; radius 12.
- Title + optional year/rating; ≤1–2 badges (DUB/SUB).
- Hover/focus: lift/scale without grid reflow; overlay Play / My List / Details; **no trailer autoplay**.
- Continue Watching: bottom progress bar; episodes show `S1 · E3`.
- Keyboard: focus ring, Enter → detail.

---

## Desktop navigation

Transparent/gradient over hero → solid elevated + blur after scroll (~64–72px).  
Logo · Home · Movies · Series · Children · Genres · More · Search · Language · Profile.

---

## Mobile navigation

Bottom tabs: Home · Movies · Series · Search · Profile.  
`safe-area-inset-bottom`; Request Movie not a tab; content padding clears nav.

---

## Movie detail layout

Full-bleed cinematic hero → meta → Play / My List / Trailer → truthful Audio/Subtitles → overview (~42rem) → cast carousel → More Like This.  
Preserve 6s backdrop → muted trailer. Player always `dir=ltr`.

Prototype uses **Interstellar (#14)** with real cast photos from production credits.

---

## Series detail layout

Same cinematic system as movies + season selector + landscape episode cards (not posters). Spec’d in doc; series interactive prototype deferred to G2 (home already shows Popular Series shelf with real series posters).

---

## RTL strategy

- FA/PS: `dir="rtl"` on document; component-level logical properties.
- Player stays LTR.
- Header/logo/actions, hero copy, shelves, arrows, footer designed — not accidental mirror.
- PS metadata: English fallback, never Persian.
- Prototypes verified: `home-desktop-fa`, `home-mobile-fa/ps`, `detail-*-fa/ps`.

---

## Performance strategy

Preserve v1.12+/v1.14 architecture: aggregated home APIs, bounded queries, lazy routes, responsive images, gzip, customer bundle budget.  
No admin imports into customer entry; no global player/trailer; no hero preload-all; no shelf auto-scroll.

---

## Accessibility strategy

Visible gold focus rings; aria-labels on icon controls; carousel buttons/dots keyboard operable; cards focusable; contrast on dark surfaces; reduced-motion cuts; TV-friendly focus foundations without building a TV app.

---

## Screenshots / prototypes path

| Screenshot | Viewport |
|---|---|
| `home-desktop-en.png` | 1440×900 |
| `home-desktop-1920-en.png` | 1920×1080 |
| `home-desktop-fa.png` | 1440×900 RTL |
| `home-mobile-en.png` | 390×844 |
| `home-mobile-fa.png` | 390×844 RTL |
| `home-mobile-ps.png` | 390×844 RTL |
| `detail-desktop-en.png` | 1440×900 Interstellar |
| `detail-desktop-fa.png` | 1440×900 RTL |
| `detail-mobile-en.png` | 390×844 |
| `detail-mobile-fa.png` | 390×844 + bottom nav |
| `detail-mobile-ps.png` | 390×844 |

Catalog titles used (real): Soulm8te, Shawshank, Star Wars, Luca, Interstellar, Inception, Toy Story, etc.

**Note:** Detail `moreLikeThis` uses real home-shelf titles when similar API is empty — layout demo only; production omits empty shelves / uses recs when present. Audio line shows **English** from spoken/original language; subtitles show **Not listed** when API has no subtitle languages (truthful — not faked FA/PS).

---

## Unresolved design decisions

1. Children nav destination (kids hub vs filter).
2. Exact **More** menu contents.
3. Notifications icon in G1 vs hide until backend.
4. Prefer `logo_url` over text title in hero when present?
5. My List on hero for anonymous users.
6. TMDB Credits as `/credits` vs About section.
7. Final Haroon Net legal/contact URLs.
8. Season selector: dropdown vs segmented when many seasons.
9. Continue Watching visibility for anonymous.
10. Confirm gold intensity against these frames.

---

## Explicit non-goals completed for G0

- ❌ No production UI rewrite  
- ❌ No G1/G2/G3 implementation  
- ❌ No T1 DB/N+1/Redis work  
- ❌ No fake catalog / fake track availability  

**Next:** human visual approval → G1 (tokens, header, homepage hero, shelves, MediaCard) in a separate PR.
