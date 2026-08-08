# Movie Detail Experience V1

**Status:** Draft planning  
**Branch:** `cursor/movie-detail-experience-4873`  
**Baseline:** after Watchlist + Continue Watching (PR #49)  
**Depends on:** real TMDB metadata already imported into the catalog

## Goal

Premium streaming-style **movie detail** page using **real TMDB metadata only**.

## Requirements

### Hero

- First **6 seconds**: full-bleed backdrop image only (no trailer chrome overlays beyond existing branding rules).
- After 6 seconds: autoplay the official **TMDB YouTube trailer** via **YouTube embed only**.
- **Never download** trailer files; never host trailer binaries on iFilm storage.
- If no official YouTube trailer exists in TMDB data: remain on backdrop (no fake video).

### Cast

- Actor carousel from **TMDB credits** (names + profile images when TMDB provides them).
- If credits are missing: omit the section — **no invented cast**.

### Similar movies

- Section from TMDB similar/recommendations, filtered to titles that **exist in the iFilm catalog**.
- Never show fake/non-catalog cards.

### Actions

- Trailer control (focus/open YouTube embed).
- Watch / Play using existing playability rules.
- Preserve Watchlist toggle once PR #49 lands (merge baseline as needed).

### Platform

- Preserve current iFilm architecture (FastAPI + React customer app).
- Full **RTL** (fa/ps) and LTR (en) support.
- No fake data paths in production UI.

## Out of scope

- Trailer download / re-encode / local packaging
- Series detail redesign (may reuse components later)
- Recommendations product engine (beyond TMDB similar)
- CDN / DRM / offline / Cast receiver

## Implementation sketch

1. **Backend** — extend public movie detail with TMDB credits payload; resolve similar TMDB IDs → local published movies only; reuse stored `trailer_provider` / `trailer_key` (YouTube only).
2. **Frontend** — hero state machine (`backdrop` 0–6s → `youtube-embed`); cast shelf; similar shelf; respect reduced-motion / autoplay policies.
3. **Tests** — timer/embed unit tests; API rejects non-YouTube providers for autoplay; no fixture fake names in production mode.

## Acceptance checklist

- [ ] Backdrop-only for 6s, then YouTube embed autoplay (muted / browser-policy compliant)
- [ ] No trailer download code paths
- [ ] Cast empty when TMDB has no credits
- [ ] Similar only catalog-backed
- [ ] en / fa / ps + RTL verified
- [ ] Watchlist / CW / Collections behavior unchanged
