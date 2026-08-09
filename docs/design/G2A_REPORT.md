# G2a Report — Movie Detail Experience V2

**Status:** Ready for human visual review (Draft PR)  
**Baseline:** production `v1.15.0`  
**Branch:** `cursor/customer-ui-v2-g2a-movie-detail-4873`  
**Scope:** Movie Detail only — **G2b not started**

Plan decisions recorded in [`G2_DETAIL_V2_PLAN.md`](./G2_DETAIL_V2_PLAN.md).

---

## Delivered

| Area | Result |
|------|--------|
| Cinematic hero | G1 `heroSizing` + scrims; logo/title; bottom-weighted |
| Trailer | 0–6s backdrop → muted nocookie embed; `controls=0`; reduced-motion skips auto; Trailer button manual restart |
| Actions | Play / Continue Watching (+%) / Watch Again / My List / Trailer / Share |
| Resume | `listContinueWatching` + `listWatchHistory` (existing progress) |
| Tracks | Truthful chips — e.g. English · فارسی دوبله · پښتو دوبله / subs English · فارسی · پښتو |
| Cast | Portrait 2:3 carousel (name + character) |
| Crew | Director + writer |
| Similar | `/movies/{id}/similar` |
| Recommendations | `/catalog/movies/{id}/recommendations` (deduped vs similar) |
| RTL | `dir` on page; FA/PS verified in screenshots |
| Player | Unchanged LTR `/player/movie/:id` |
| Reviews placeholder | Removed |

---

## Screenshots

`docs/design/screenshots/g2a/` · artifacts `/opt/cursor/artifacts/customer-ui-v2-g2a/`

| Shot |
|------|
| `movie-desktop-1920-en.png` |
| `movie-desktop-1440-en.png` |
| `movie-desktop-1440-fa.png` |
| `movie-desktop-1440-ps.png` |
| `movie-mobile-430-en.png` |
| `movie-mobile-390-en.png` |
| `movie-mobile-390-fa.png` |
| `movie-mobile-390-ps.png` |
| `movie-desktop-1440-en-trailer-trailer.png` (mode after ~6s) |
| `movie-desktop-1440-en-cast.png` |

Capture target: Interstellar (`/movie/14`) via local `VITE_DATA_MODE=api` build proxied to `ifilm.af` APIs.

---

## Performance

| Metric | Value |
|--------|-------|
| Main JS (local api build) | ~310 KB raw · ~100 KB gzip |
| Detail chunk | lazy `Browse-*.js` (~37 KB / ~11 KB gzip) |
| Page-load TMDB | none (cached credits/artwork) |
| Images | hero `eager`+srcset; cast/similar lazy |

No new libraries.

---

## Tests

- `MovieDetailHero.test.tsx` — backdrop→trailer, mute/pause/backdrop, Continue/Watch Again, cast/tracks/similar  
- `catalogDemoUi.test.tsx` — updated for track meta + mocked recs/CW APIs  
- `catalogAvailability` — pass  

---

## Remaining findings (non-blocking)

1. **Headless YouTube:** muted autoplay embed may show Google “confirm you’re not a bot” in Chromium headless; transition still sets `data-hero-mode=trailer`. Real browsers typically play muted.  
2. Interstellar fixture is **demo-owned** → primary CTA shows **Play Demo Clip** (correct gating). Resume/Watch Again verified in unit tests with injected watch state.  
3. Audio/subtitle chips appear only when availability payloads list tracks (hero meta).  

---

## Ready gate

| Gate | Status |
|------|--------|
| Approved trailer policy (6s muted) | ✓ |
| Resume from existing progress | ✓ |
| Cast portraits | ✓ |
| Truthful tracks | ✓ |
| Similar + recommendations | ✓ |
| RTL FA/PS screenshots | ✓ |
| Desktop 1920/1440 + mobile 430/390 | ✓ |
| No G2b / no prod deploy | ✓ |

**STOP — do not start G2b until G2a approved.**

---

*End of G2A_REPORT.md*
