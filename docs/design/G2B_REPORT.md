# G2b — Series Detail Experience V2 Report

**Status:** READY for human visual approval (Draft PR)  
**PR:** https://github.com/nimroozy/ifilm2026/pull/75  
**Branch:** `cursor/g2b-series-detail-impl-4873`  
**Head SHA:** `89800bd4588f9100d2c7b0f493a6c9aa74e7d382`  
**Baseline:** production `v1.16.0`  
**Planning PR (unchanged):** #74  

**Do not merge or deploy** until human approval.

---

## Product decisions implemented

| # | Decision | Result |
|---|----------|--------|
| 1 | Series trailer **button-only** (no 6s autoplay) | `data-trailer-policy="button-only"`; unit test asserts no timed transition; G2a movie 6s behavior unchanged |
| 2 | Exclusive primary CTA | Continue → Next → Watch Again → Play (one only) |
| 3 | Next episode by season/episode order | Unit-tested incl. S01E10 → S02E01; skips unplayable |
| 4 | Credits detail-only | `series_out(..., include_credits=True)` on public/admin detail only |

---

## API changes

| Change | Detail |
|--------|--------|
| `SeriesOut.credits` / `credits_synced_at` | Additive fields; default empty |
| `series_out(include_credits=False)` | Credits loaded only when `True` |
| `GET /api/series/{id}` | Passes `include_credits=True` |
| Admin series get/create/update | `include_credits=True` |
| List/card/home/search callers | Remain without credits queries |

**No migration** — uses existing `series_cast_credits`.

### Credit serialization strategy

Opt-in flag on `series_out` (preferred over a new DTO type) so browse/list/search that still call `series_out` do not pay cast cost. Card path `series_card_out` explicitly sets `credits=[]`.

### Query-count impact

| Surface | Result |
|---------|--------|
| `GET /api/series` browse | Asserts **no** `series_cast_credits` in SQL (`test_series_list_card_query_ceiling`) |
| `GET /api/series/{id}` detail | Single credits list query (`test_series_detail_credits`) |
| Episode season fetch | Pre-existing per-episode playability/track probes remain; G2b reduces blast radius by **season-scoped** fetch only |

---

## Frontend architecture

- New `SeriesDetailView.tsx` (cinematic hero, episodes, cast, recs)
- Thin `SeriesDetailsPage` loader in `Browse.tsx`
- Season-scoped `fetchSeasonEpisodes` + in-memory cache by season
- Shared `CastRail` / `CastCard` extracted; `MovieDetailView` imports shared rail (G2a trailer autoplay tests still pass)
- CTA helpers in `lib/seriesDetailPlayback.ts`
- Incomplete progress also resolved from **watch history** when CW rail is capped

---

## Real series used (production catalog via local UI)

| Series | ID | Notes |
|--------|----|------|
| **Game of Thrones** | `4` | Primary QA — 2 seasons, trailer, logo, playable S01E01–E02 (demo clips), recommendations |
| Breaking Bad | `8` | 2 seasons; fewer playable episodes / no trailer key |

**Cast note:** Production DB currently has **zero** rows in `series_cast_credits` for these titles. Cast rail verified with detail payload injection matching the new API shape; after deploy, run admin TMDB credits refresh for showcase series.

**Progress:** QA subscriber `qa-rec-personalized` (id 4) — incomplete progress on GoT S01E02 used for Continue CTA (~44%).

---

## CTA state results

| State | Evidence |
|-------|----------|
| Continue Watching S01E02 | Live screenshot + authenticated history/CW mapping |
| Next Episode | Unit tests (same-season + season boundary) |
| Watch Again | Unit tests (no next playable) |
| Play | Unit tests (no history) |
| Exclusive CTA | Component tests |

---

## Season selection

| Viewport | Control | Evidence |
|----------|---------|----------|
| Desktop | Compact select (`Season N · count`) | Screenshots |
| Mobile | Bottom sheet | `series-mobile-390-en-season-sheet.png` |
| Default season | Season of continue/next episode | GoT opened on Season 1 with S01E02 progress |

---

## Episode progress / tracks / recs / trailer

- Episode rows: `S01E01` codes, thumbs, duration, description clamp, Resume/Play, thin gold progress on in-progress E02
- Series-level tracks omit empty groups (GoT probe often empty beyond source metadata)
- More Like This: recommendations shelf populated (series-only)
- Trailer: secondary button → muted in-hero trailer on click; no autoplay on load

---

## RTL

FA and PS desktop/mobile screenshots captured (`dir=rtl` chrome). Player route unchanged / LTR.

---

## Performance

Anonymous first open (target): series + seasons + selected-season episodes + recommendations (~4).  
Authenticated adds: CW + history + watchlist membership (no per-episode progress HTTP).

---

## Screenshots

Under `docs/design/screenshots/g2b/` and `/opt/cursor/artifacts/g2b/`:

- `series-desktop-1920-en.png`
- `series-desktop-1440-en-continue.png`
- `series-desktop-1440-fa.png` / `series-desktop-1440-ps.png`
- `series-mobile-430-en.png` / `series-mobile-390-en.png`
- `series-mobile-390-fa.png` / `series-mobile-390-ps.png`
- `series-mobile-390-en-season-sheet.png`
- `series-desktop-1440-en-episodes.png`
- `series-desktop-1440-en-cast.png` (injected credits — see note)
- `series-desktop-1440-en-recs.png`
- `series-desktop-1440-en-trailer.png`

---

## Tests

- Backend: `test_series_detail_credits.py`, series list query ceiling update
- Frontend: `seriesDetailPlayback.test.ts`, `SeriesDetailHero.test.tsx`, `MovieDetailHero.test.tsx` (G2a regression)

---

## Remaining findings (accepted / follow-up)

| Level | Finding |
|-------|---------|
| MED | Production `series_cast_credits` empty for showcase titles — needs admin TMDB credits sync after deploy |
| MED | GoT S02 episodes not playable — season-boundary Next cannot be shown on this title live; covered by unit tests |
| LOW | Season label uses `N Season` without pluralization polish |
| LOW | Episode list still uses pre-existing per-episode playability/track SQL on the season fetch (scoped to one season) |
| INFO | Trailer button wraps under My List on narrow hero widths — acceptable flex-wrap |

No BLOCKER / HIGH found for Ready gate.

---

## Stop

Await human visual approval. **Do not merge. Do not deploy.**
