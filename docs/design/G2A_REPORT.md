# G2a Report — Movie Detail Experience V2

**Status:** Ready for final human approval (Draft PR — **do not merge yet**)  
**Baseline:** production `v1.15.0`  
**Branch:** `cursor/customer-ui-v2-g2a-movie-detail-4873`  
**Final head:** `f80b241c62daf36ce506e58b73546e379a54625c`  
**Scope:** Movie Detail only — **G2b not started**

Plan decisions recorded in [`G2_DETAIL_V2_PLAN.md`](./G2_DETAIL_V2_PLAN.md).

---

## Real-content fixture

| Field | Value |
|------|--------|
| Movie | **Soulm8te** (`/movie/31`, TMDB `1307118`) |
| Ownership | `demo_owned=false` — normal **Play** (not Play Demo Clip) |
| Package | playable non-demo session (`is_demo_only=false`) |
| Trailer | YouTube nocookie `DF9I1wLlXbk` |
| Credits | 24 TMDB credits synced; UI shows top **16** portraits + initials fallback |
| Tracks (Soulm8te) | Subtitles: **فارسی** only (no invented FA/PS audio) |
| Multi-track check | Catalog QA title `/movie/39` — Audio: English · فارسی دوبله · پښتو دوبله / Subs: English · فارسی · پښتو |

Do not use Interstellar for G2a Ready screenshots (demo-owned → Demo Clip CTA).

---

## CTA hierarchy (authenticated)

| State | Primary | Secondary | Tertiary |
|------|---------|-----------|----------|
| No progress | **Play** | My List · Trailer | Share icon |
| Incomplete (~47%) | **Continue Watching 47%** | My List · Trailer | Share icon |
| Completed | **Watch Again** | My List · Trailer | Share icon |

Verified: exactly one primary playback CTA; no simultaneous Play/Continue/Watch Again.

---

## Resume QA

Subscriber: `qa-rec-personalized` (minted JWT).

1. Seeded backend progress at **55s / 46.76%** on asset `72c4a24f-35fe-4dcf-af7a-e24a1e726a03`
2. Detail reload shows **Continue Watching** + progress bar
3. Playback session create succeeds (`has_url`, not demo-only)
4. `player_path` = `/player/movie/31`
5. Complete → detail shows **Watch Again** (startOver navigation wiring covered by unit tests + `goPlay(true)`)
6. Start over / clear history → **Play**

Player remains LTR `/player/movie/:id`. Full HLS seek inside local proxy was not used (stream proxy stalls headless Chromium); resume position is backend-authoritative via `/api/me/watch-progress` + existing `watchProgress` player tests.

---

## Delivered

| Area | Result |
|------|--------|
| Cinematic hero | G1 `heroSizing` + scrims; logo/title; bottom-weighted |
| Trailer | 0–6s backdrop → muted nocookie embed; `controls=0`; reduced-motion skips auto |
| Actions | Single primary + My List + Trailer; Share icon-only |
| Tracks | Truthful chips; omit `und`/unknown; omit empty subtitle row |
| Cast | Portrait 2:3 rail (name + character); missing-photo initials |
| Crew | Director/Writer omitted when blank (Soulm8te has none) |
| Similar / Recs | Similar API + recommendations; **deduped** (recs → Luca only vs similar set) |
| RTL | FA/PS `dir=rtl`; FA localized title **سول‌میت**; PS title English fallback |
| Overview | Desktop + mobile collapse (`More`) |
| Reviews placeholder | Removed |

---

## Screenshots

`docs/design/screenshots/g2a/` · artifacts `/opt/cursor/artifacts/customer-ui-v2-g2a/`  
Machine summary: `/opt/cursor/artifacts/customer-ui-v2-g2a/REAL_CONTENT_QA.json`

| Shot | Notes |
|------|--------|
| `movie-desktop-1920-en.png` | Play state |
| `movie-desktop-1440-en.png` | Continue / backdrop |
| `movie-desktop-1440-en-continue.png` | Continue Watching 47% |
| `movie-desktop-1440-en-trailer-trailer.png` | `data-hero-mode=trailer` (~6s) |
| `movie-desktop-1440-en-cast.png` | Cast + similar |
| `movie-desktop-1440-en-watch-again.png` | Watch Again |
| `movie-desktop-1440-fa.png` | RTL FA |
| `movie-mobile-430-en.png` | Continue |
| `movie-mobile-390-en.png` | Continue |
| `movie-mobile-390-fa.png` | RTL FA |
| `movie-mobile-390-ps.png` | RTL PS |
| `movie-desktop-1440-en-multitrack-qa.png` | Multi-track truthfulness (`/movie/39`) |

---

## Performance

| Metric | Value |
|--------|-------|
| Main JS (local api build) | ~311 KB raw · ~98–100 KB gzip (`index-Dx_x1-4s.js`) |
| Detail lazy chunk | `Browse-*.js` ~37 KB / ~11 KB gzip |
| Page-load TMDB API | none |
| `/original/` artwork | none observed |
| Images | hero eager+srcset; cast/similar lazy |

No new libraries.

---

## Tests / CI

- `MovieDetailHero.test.tsx` — trailer, Continue/Watch Again exclusivity, Share icon, cast/tracks
- `catalogAvailability.test.ts` — omit `und` placeholders; multi-track labels
- `catalogDemoUi.test.tsx` — demo vs playable gating
- GitHub `stabilize` checks: **pass** on head `f80b241`

---

## Trailer (browser)

- Transition to `data-hero-mode=trailer` after ~6s with muted `controls=0` embed URL
- Headless/automation often shows YouTube “Video unavailable” / bot interstitial; **backdrop remains** (never blank hero); Unmute/Pause/Show backdrop controls present
- Reduced-motion path skips auto trailer (policy)

---

## Remaining findings (non-blocking)

1. **MED — Mobile action height ~168px** on 390/430: primary full-width Continue + secondary row (My List / Trailer / Share). Acceptable cinematic stack; not a six-button toolbar.
2. **MED — YouTube embed in automation:** may show unavailable; production browsers typically play muted; fallback safe.
3. Similar shelf still lists catalog QA title `v1140 MultiTrack QA…` because it is published — truthful catalog, not fabricated metadata.
4. Soulm8te has no Director/Writer fields — correctly omitted.

**No BLOCKER / HIGH.**

---

## Ready gate

| Gate | Status |
|------|--------|
| Real non-demo movie looks correct | ✓ Soulm8te |
| Authenticated resume / Continue CTA | ✓ |
| Primary CTA hierarchy clean | ✓ |
| Truthful tracks | ✓ Soulm8te + multi-track QA |
| Cast looks professional | ✓ portraits + fallbacks |
| Trailer fallback safe | ✓ |
| Mobile not overcrowded | ✓ (MED note only) |
| FA/PS intentional | ✓ |
| CI green | ✓ |
| No BLOCKER/HIGH | ✓ |
| No G2b / no auto-merge | ✓ |

**STOP — do not start G2b until G2a is human-approved. Do not auto-merge.**

---

*End of G2A_REPORT.md*
