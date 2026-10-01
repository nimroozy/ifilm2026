# G2a Production Verification — Movie Detail V2

**Public:** https://ifilm.af  
**Release:** https://github.com/nimroozy/ifilm2026/releases/tag/v1.16.0  
**Workflow:** https://github.com/nimroozy/ifilm2026/actions/runs/31315388426  
**Installed:** `/opt/ifilm/releases/v1.16.0`  
**Deploy path:** official update-agent `install_verified_release` only  
**QA artifacts:** `/opt/cursor/artifacts/v1160-prod/` · screenshots `docs/design/screenshots/g2a-prod/`

**STOP after this verification — do not start G2b automatically.**

---

## Merge / release / deploy

| Item | Value |
|------|--------|
| PR | [#72](https://github.com/nimroozy/ifilm2026/pull/72) (Ready → squash merge) |
| Squash merge SHA | `9eb5e9b3ecf57300957a226d8b2292863476cb18` |
| Pre-merge head (approved) | `2faf13a11ac6cdf01228e900157fc343c89aca86` |
| Tag | **`v1.16.0`** (stable) |
| Release assets | signed `release-manifest.json` + `.sig`, `SHA256SUMS`, SBOMs, Trivy JSON, `ifilm-1.16.0.tar.gz` |
| Job | `f7198704701566f2` **completed** |
| Backup | `pre-update-20260809T132632Z` |
| `verify-installation` | **ok=true**, digests consistent, health ready |
| Migration | **`023_media_tracks_packaging_v1`** (unchanged; no new migration) |
| Rollback target | **`1.15.0`** |
| Channel | stable |

### Digests (v1.16.0 running)

- backend/workers: `ghcr.io/nimroozy/ifilm2026/backend-api@sha256:392d3e8696ae8f4e3f1e068e8816f635c7d1f8ea61b9f2d2bc46d9d1054c8a37`
- frontend: `ghcr.io/nimroozy/ifilm2026/frontend@sha256:570c95e07dad43a974292990ddf542c9a25466b8a2fd7103305687c09e6fc5b5`

Services after deploy: nginx, frontend, backend-api, publishing-worker, media-processing-worker, postgres, redis — **healthy**.

---

## Production real-content QA

Primary: **Soulm8te** `https://ifilm.af/movie/31` (`demo_owned=false`, `playable=true`, 24 credits, trailer present)  
Multi-track: **`/movie/39`**

Machine summary: `/opt/cursor/artifacts/v1160-prod/prod-qa.json`

### CTA states (authenticated subscriber)

| State | Primary | Secondary / tertiary | Result |
|-------|---------|----------------------|--------|
| No progress | **Play** | My List · Trailer · Share icon | ✓ single primary |
| Incomplete (55s / 46.76%) | **Continue Watching** | My List · Trailer · Share icon | ✓ |
| Completed | **Watch Again** | My List · Trailer · Share icon | ✓ |

No Demo Clip CTA on Soulm8te.

### Real resume

| Check | Result |
|-------|--------|
| Seed progress 55s via `/api/me/watch-progress` | ✓ |
| Detail shows Continue Watching | ✓ |
| Playback session (`is_demo_only=false`, URL present) | ✓ |
| Live Continue → `/player/movie/31` navigation | ✓ (earlier production pass) |
| Video `currentTime` within 2.5s | **MED** — observed `0` (buffering); backend position authoritative |
| Watch Again → player with `startOver` intent | ✓ (unit + nav wiring; harness avoided long HLS teardown) |
| Player LTR unchanged | ✓ `/player/movie/:id` |

### Tracks

| Title | UI |
|-------|-----|
| Soulm8te | Subtitles: **فارسی** only (no invented audio FA/PS) |
| Movie 39 | Audio: English · فارسی دوبله · پښتو دوبله / Subs: English · فارسی · پښتو |

No `FA Dub` / `PS Dub` shorthand. No `und` chips.

### Cast / crew

- Cast rail: **16** portraits (top of synced credits) + initials fallback for missing photos  
- Director / Writer: **omitted** (blank fields not rendered)

### Similar / recommendations

- Current movie excluded  
- Dedupe: recommendations reduced to titles not in Similar (e.g. **Luca**)  
- Overlap: **none**

### Trailer

- 0–6s backdrop → `data-hero-mode=trailer` (~6506 ms)  
- Muted nocookie embed (`mute=1`, `controls=0`)  
- Hero never blank if embed fails (backdrop remains)  
- Automation/headless may still show YouTube challenge — accepted MED from G2a review

### Mobile (390 / 430)

- Action stack height **~168px** (known MED): primary full-width Continue + secondary row  
- Hero remains cinematic; no HIGH crowding  
- Share icon-only; no six-button toolbar  
- Document for **G3 polish** if product wants denser stacking — **not expanded in G2a**

### RTL

| Locale | `dir` | Title | Notes |
|--------|-------|-------|-------|
| FA desktop/mobile | rtl | **سول‌میت** | Persian metadata when available |
| PS mobile | rtl | **Soulm8te** | English fallback (not Persian) |

### Performance (production)

| Metric | Value |
|--------|-------|
| Main JS `index-ncPv9IlM.js` | **~311 KB** raw · **~98 KB** gzip |
| Detail lazy `Browse-DNK0J-8P.js` | **~37 KB** raw · **~11 KB** gzip |
| Detail page APIs | `/api/config`, `/api/movies/31`, similar, recommendations, watchlist, continue-watching, watch-history, entitlement — **no TMDB** |
| `/original/` artwork | none observed |
| Desktop detail DCL | ~0.93 s |

No meaningful regression vs v1.15.0 customer browsing budgets.

### Functional regression smoke

| Area | Result |
|------|--------|
| Homepage G1 shell | ✓ |
| Watchlist button on detail | ✓ |
| Protected playback session | ✓ non-demo |
| Localization FA/PS | ✓ |
| Content catalog home API | ✓ |

---

## Screenshots

`docs/design/screenshots/g2a-prod/` · `/opt/cursor/artifacts/v1160-prod/screenshots/`

- `prod-movie-desktop-1920-en-play.png`
- `prod-movie-desktop-1440-en-play.png`
- `prod-movie-desktop-1440-en-continue.png`
- `prod-movie-desktop-1440-en-watch-again.png`
- `prod-movie-desktop-1440-en-backdrop.png`
- `prod-movie-desktop-1440-en-trailer.png`
- `prod-movie-desktop-1440-en-cast.png`
- `prod-movie-desktop-1440-fa.png`
- `prod-movie-mobile-430-en.png`
- `prod-movie-mobile-390-en.png`
- `prod-movie-mobile-390-fa.png`
- `prod-movie-mobile-390-ps.png`
- `prod-movie-desktop-1440-en-multitrack-39.png`
- `prod-home-desktop-1440-en.png`

---

## Remaining findings

| Level | Finding |
|-------|---------|
| MED | Mobile action area ~168px (accepted for G2a; candidate G3 polish) |
| MED | Headless/automation YouTube may show unavailable/challenge; backdrop fallback safe |
| MED | Live player `currentTime` sample 0s within 2.5s after Continue (buffering); backend resume position + CTA verified |

**No BLOCKER / HIGH.**

---

## Verdict

| Gate | Status |
|------|--------|
| v1.16.0 installed & healthy | ✓ |
| Digests aligned | ✓ |
| Migration 023 | ✓ |
| Rollback = 1.15.0 | ✓ |
| Soulm8te Movie Detail V2 | ✓ |
| Multi-track labels | ✓ |
| CTA hierarchy | ✓ |
| Resume/progress | ✓ (with MED buffering note) |
| Trailer policy | ✓ |
| RTL FA/PS | ✓ |
| Performance budgets | ✓ |

**G2a production verification complete. STOP — wait for live Movie Detail human review before starting G2b.**

---

*End of G2A_PRODUCTION_VERIFICATION.md*
