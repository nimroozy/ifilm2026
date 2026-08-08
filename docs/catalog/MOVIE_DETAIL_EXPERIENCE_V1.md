# Movie Detail Experience V1

**Status:** Implemented (Draft PR)  
**Branch:** `cursor/movie-detail-experience-4873` (rebased on Watchlist PR #49)  
**Migration:** `018_movie_detail_experience_v1` (revises `017_watchlist_v1`)  
**Depends on:** PR #49 Watchlist (`017_watchlist_v1`); real TMDB metadata already imported into the catalog

## Goal

Premium streaming-style **movie detail** page using **real TMDB metadata only**.

## Delivered

### Hero

- First **6 seconds**: full-bleed backdrop + title/rating/year/runtime/genres/description/actions (no trailer autoplay).
- After 6 seconds: muted YouTube embed autoplay from stored TMDB trailer metadata.
- Controls: mute/unmute, pause, return to backdrop.
- `prefers-reduced-motion`: stay on backdrop.
- No trailer → remain on backdrop; no fake video.

### Content readiness

- **Play** only when `published` + playable flags.
- Else trailer → **Watch Trailer**.
- Else → **Coming Soon** (never “Full Movie Unavailable”).

### Cast

- Persisted TMDB credits (`movie_cast_credits`) — not fetched on every page load.
- Horizontal carousel: photo, actor name, character.

### Similar movies

- `GET /api/movies/{id_or_slug}/similar`
- Priority: collection → genres → TMDB similar ∩ catalog → popular fallback.
- Published catalog titles only; no duplicates; no fake cards.

### Admin

- Movie edit shows trailer / cast / similar status.
- **Refresh TMDB Details** (`POST /api/admin/tools/tmdb/refresh-title`) updates TMDB-owned trailer/credits only.

### Player

- Uses existing `/player/movie/:id` path; entitlement/playback/security unchanged.

## Acceptance checklist

- [x] Backdrop-only for 6s, then YouTube embed autoplay (muted)
- [x] No trailer download code paths
- [x] Cast empty when TMDB has no credits
- [x] Similar only catalog-backed
- [x] Play gated by published + playable
- [ ] en / fa / ps + RTL browser QA
- [ ] Watchlist / CW merge baseline (PR #49 separate)
