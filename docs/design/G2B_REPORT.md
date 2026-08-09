# G2b — Series Detail Experience V2 Report

**Status:** READY for human visual approval (Draft PR)  
**PR:** https://github.com/nimroozy/ifilm2026/pull/75  
**Branch:** `cursor/g2b-series-detail-impl-4873`  
**Head SHA:** `0a39c5a62ad4b6cacf6e4979f15c10b6f898a2a0`  
**Baseline:** production `v1.16.0`  
**Planning PR (unchanged):** #74  

**Do not merge or deploy** until human approval.

---

## CI / Ready gate (local + GitHub)

| Gate | Result |
|------|--------|
| Frontend lint | PASS (`eslint --quiet ./src`) |
| Frontend typecheck | PASS (`tsc -b`) — prior CI failure fixed |
| Frontend tests | PASS (246) |
| Frontend build | PASS (`vite build`) |
| Secret build scan | PASS (`scan-build-secrets`) |
| Customer initial JS budget | PASS (raw ~692 KB; fail budget 800 KB) |
| Backend CI (GitHub `quality` on prior head `0c5aa6f`) | SUCCESS |
| Backend series credit tests | PASS (`test_series_detail_credits.py`) |
| Backend query-ceiling / list perf | PASS (`test_catalog_list_perf.py`) |
| Episode season SQL measurement | PASS (`test_series_episode_list_query_counts.py`) — flat after batch fix |
| G2a CastRail / Movie Detail regression | PASS (`MovieDetailHero.test.tsx` + movie 6s trailer in `catalogDemoUi.test.tsx`) |
| BLOCKER / HIGH | None |

Prior Frontend CI failure at head `0c5aa6f` was typecheck-only (`stabilize`). Re-verify GitHub Frontend CI on this tip after push.

---

## Typecheck fixes (exact)

| Error | Fix |
|-------|-----|
| A) `SeriesDetailView` EpisodeRow `movieDetailTrackGroups` missing `multiAudio` | Supplied required `AvailabilityBadgeLabels.multiAudio` (`'Multi Audio'`) — same convention as `MovieDetailView`. Did **not** weaken the shared contract. |
| B) `CatalogSeries` / mock `Series` lacked `endYear` | API already exposes `end_year`; `mapSeriesDto` maps `endYear`. Added optional `endYear?: number | null` on mock `Series` so the union type matches real DTO mapping. UI still shows start year only when `endYear` is absent/equal. **No invented backend field.** |
| C) `Browse.tsx` undefined `canPlayFullMovie` (2 call sites) | Restored import from `@/lib/catalogPresentation` (canonical helper). No duplicated playability logic in Browse. |

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
| `GET /api/series/{id}/episodes` (+ public season episodes) | Uses batched `episodes_list_out` (playability / packages / tracks / i18n) |

**No migration** — uses existing `series_cast_credits`.

### Credit serialization strategy

Opt-in flag on `series_out` (preferred over a new DTO type) so browse/list/search that still call `series_out` do not pay cast cost. Card path `series_card_out` explicitly sets `credits=[]`.

### Query-count impact

| Surface | Result |
|---------|--------|
| `GET /api/series` browse | Asserts **no** `series_cast_credits` in SQL (`test_catalog_list_perf.py`) |
| `GET /api/series/{id}` detail | Single credits list query (`test_series_detail_credits`) |
| Episode season fetch | **Batched** — see measurements below |

---

## Selected-season episode SQL measurements

Instrument: `GET /api/series/{id}/episodes?season=1` with assets + audio/subtitle tracks seeded.

### Before batch fix (linear N+1)

| Episodes | Total SQL | Assets | Tracks | Packages | Other | ~per ep |
|---------:|----------:|-------:|-------:|---------:|------:|--------:|
| 3 | 26 | 9 | 3 | 6 | 8 | 8.7 |
| 10 | 82 | 30 | 10 | 20 | 22 | 8.2 |
| 20 | 162 | 60 | 20 | 40 | 42 | 8.1 |

**Conclusion (pre-fix):** query count grew approximately linearly with episode count (~8 statements/episode for playability + packages + tracks). Season-scoped fetch reduced blast radius but did **not** remove N+1.

### After batch fix (`episodes_list_out`)

| Episodes | Total SQL | Assets | Tracks | Packages | Translations | Other |
|---------:|----------:|-------:|-------:|---------:|-------------:|------:|
| 3 | **6** | 1 | 1 | 1 | 1 | 2 |
| 10 | **6** | 1 | 1 | 1 | 1 | 2 |
| 20 | **6** | 1 | 1 | 1 | 1 | 2 |

**N+1 conclusion:** **Fixed.** Season episode list SQL is effectively bounded (flat at 6 statements across 3/10/20 episodes). Bulk preload covers playability assets, active packages, media tracks, and episode translations. Guarded by `test_series_episode_list_query_counts.py`.

---

## Credits refresh procedure (existing — no second pipeline)

| Item | Detail |
|------|--------|
| Admin action / API | `POST /api/admin/tools/tmdb/refresh-title` body `{ "media_type": "series", "entity_id": <id> }` |
| Implementation | `refresh_series_tmdb_details` → `sync_series_credits` (`app/services/tmdb/refresh_title.py`) |
| Required permission | `require_tmdb_admin`: any of `catalog.edit`, `movies.manage`, `movies` |
| Present in `v1.16.0`? | **Yes** — API + sync already shipped; G2b only exposes credits on series detail responses |
| UI affordance | Movie form has “Refresh TMDB Details”; Series form currently only has translations refresh. Use API (or equivalent admin tooling) for series credits — **do not** build a second sync pipeline |
| Safe before deploy? | **Yes to persist** into existing `series_cast_credits` (no schema change). Cast rail consumption needs G2b detail API (`include_credits=True`) |
| Safe after deploy? | **Yes** |

### Real cast production verification (not injection)

Injection screenshots prove **component QA only**. Production currently has **zero** `series_cast_credits` for showcase titles.

**Explicit post-deploy verification path:**

1. Deploy G2b
2. Refresh credits for QA/showcase series via `POST /api/admin/tools/tmdb/refresh-title` (`media_type=series`)
3. Verify `GET /api/series/{id}` returns non-empty `credits` / `credits_synced_at`
4. Verify Series Detail cast rail with that real payload
5. Only then mark production cast verification complete

Optional: run the refresh **before** deploy to warm the table; step 3–4 still require the new detail API.

---

## Next Episode live limitation

- Unit test keeps **S01E10 → S02E01** season-boundary coverage (`seriesDetailPlayback.test.ts`).
- GoT production fixture cannot demonstrate live season-boundary Next (S02 not playable).
- After deploy: if a real series with a playable season boundary exists, perform live QA; otherwise record as **unit/integration verified, not live verified**.
- Do **not** modify production catalog solely to manufacture this test.

---

## G2a CastRail regression

Shared `CastRail` extraction is consumed by `MovieDetailView`. Re-run results:

| Check | Result |
|-------|--------|
| Movie Detail loads / hero | PASS (`MovieDetailHero.test.tsx`) |
| Movie cast rail | Shared component path; hero suite green |
| FA/PS direction | Unchanged RTL chrome (prior G2b screenshots + existing locale tests) |
| Movie 6s trailer autoplay | PASS (`catalogDemoUi.test.tsx` timed transition + autoplay embed) |
| Movie Detail CTA | No regression in hero suite |

---

## Frontend architecture

- New `SeriesDetailView.tsx` (cinematic hero, episodes, cast, recs)
- Thin `SeriesDetailsPage` loader in `Browse.tsx`
- Season-scoped `fetchSeasonEpisodes` + in-memory cache by season
- Shared `CastRail` / `CastCard` extracted; `MovieDetailView` imports shared rail
- CTA helpers in `lib/seriesDetailPlayback.ts`
- Incomplete progress also resolved from **watch history** when CW rail is capped

---

## Real series used (production catalog via local UI)

| Series | ID | Notes |
|--------|----|------|
| **Game of Thrones** | `4` | Primary QA — 2 seasons, trailer, logo, playable S01E01–E02 (demo clips), recommendations |
| Breaking Bad | `8` | 2 seasons; fewer playable episodes / no trailer key |

**Cast evidence distinction:** screenshots with cast used **injected** detail credits for component QA. Real persisted production credits: **not verified** until post-deploy refresh path above.

**Progress:** QA subscriber `qa-rec-personalized` (id 4) — incomplete progress on GoT S01E02 used for Continue CTA (~44%).

---

## CTA state results

| State | Evidence |
|-------|----------|
| Continue Watching S01E02 | Live screenshot + authenticated history/CW mapping |
| Next Episode | Unit tests (same-season + season boundary); **not live verified** on GoT |
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
Season episode list SQL bounded at **6** statements after batching (independent of episode count in measured range).

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
- `series-desktop-1440-en-cast.png` (**injected** credits — component QA only)
- `series-desktop-1440-en-recs.png`
- `series-desktop-1440-en-trailer.png`

---

## Tests

- Backend: `test_series_detail_credits.py`, `test_catalog_list_perf.py`, `test_series_episode_list_query_counts.py`
- Frontend: `seriesDetailPlayback.test.ts`, `SeriesDetailHero.test.tsx`, `MovieDetailHero.test.tsx`, `catalogDemoUi.test.tsx` (G2a trailer)

---

## Remaining findings (accepted / follow-up)

| Level | Finding |
|-------|---------|
| MED | Production `series_cast_credits` empty for showcase titles — real cast verification is **post-deploy** via existing TMDB refresh (injection ≠ production verification) |
| MED | GoT S02 not playable — season-boundary Next is unit/integration verified, **not live verified**; do not manufacture catalog for it |
| LOW | Season label uses `N Season` without pluralization polish |
| INFO | Trailer button wraps under My List on narrow hero widths — acceptable flex-wrap |

No BLOCKER / HIGH found for Ready gate.

---

## Stop

Await human visual approval. **Do not merge. Do not deploy.**
