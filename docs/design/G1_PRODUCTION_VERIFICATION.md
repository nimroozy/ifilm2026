# G1 Production Verification — v1.15.0

**Date:** 2026-08-09  
**Train:** Customer UI V2 — Foundation + Homepage (G1)  
**Status:** **PASSED** — production GUI verified on https://ifilm.af  
**Do not start G2** until human review of this production GUI.

Artifacts: `/opt/cursor/artifacts/v1150-prod/`  
Screenshots: `docs/design/screenshots/g1/production/`

---

## Merge

| Item | Value |
|------|-------|
| PR | [#69](https://github.com/nimroozy/ifilm2026/pull/69) |
| Squash title | `feat: implement customer UI v2 foundation and homepage` |
| Merge SHA | `5daa0e8b9069c19db75135dec8123555030cbd84` |
| Mergeable / CI | MERGEABLE · Frontend CI green |
| Review threads | none |
| Head at merge | `cb1203cb69e8f9ca3e0f19cbe244c9e4f19d5cf3` (unchanged) |
| Scope | Frontend + design docs only |
| Backend / migrations | **none** |

---

## Release

| Item | Value |
|------|-------|
| Version | **v1.15.0** |
| Tag / workflow | https://github.com/nimroozy/ifilm2026/actions/runs/31311127454 |
| Release | https://github.com/nimroozy/ifilm2026/releases/tag/v1.15.0 |
| Commit | `5daa0e8b9069c19db75135dec8123555030cbd84` |
| Migration head | `023_media_tracks_packaging_v1` (unchanged) |
| Channel | `stable` |
| Rollback | `application_only` → **1.14.3** |

### Assets present

- `release-manifest.json` + `.sig` (signed)
- `ifilm-1.15.0.tar.gz`
- `SHA256SUMS`
- `ifilm-1.15.0-backend.sbom.spdx.json` / frontend SBOM
- `backend-trivy.json` / `frontend-trivy.json`

### Digests deployed

| Service | Digest |
|---------|--------|
| backend-api / media-processing / publishing | `sha256:71b0f97a1a722523d402bcd1c175a778639460080e74f7270b4b3ffd035e171e` |
| frontend | `sha256:5202d2ecec5c5f4d33d92663efdc5fef2766fef8f3339a867713c32aed59752f` |

---

## Production deploy

Deployed via **ifilm-update-agent** only (`install_verified_release`).

| Check | Result |
|-------|--------|
| Preflight | ok (1.14.3 → 1.15.0, signature verified) |
| Install job | `2c07332b2bef3168` **completed** |
| Backup id | `pre-update-20260809T114325Z` |
| `verify-installation` | **ok** · digests consistent · health ready |
| Installed version | **1.15.0** |
| Migration | **023_media_tracks_packaging_v1** |
| Rollback target | **1.14.3** |
| Channel | stable |

### Service health (all healthy)

| Service | Status |
|---------|--------|
| backend-api | healthy |
| frontend | healthy |
| nginx | healthy |
| postgres | healthy |
| redis | healthy |
| media-processing-worker | healthy |
| publishing-worker | healthy |

Footer reports **Version 1.15.0**.

---

## Production screenshots

| Shot | Path |
|------|------|
| Desktop EN 1440×900 | `docs/design/screenshots/g1/production/home-desktop-en-1440.png` |
| Desktop FA 1440×900 | `docs/design/screenshots/g1/production/home-desktop-fa-1440.png` |
| Mobile EN 390×844 | `docs/design/screenshots/g1/production/home-mobile-en-390.png` |
| Mobile FA 390×844 | `docs/design/screenshots/g1/production/home-mobile-fa-390.png` |
| Mobile PS 390×844 | `docs/design/screenshots/g1/production/home-mobile-ps-390.png` |
| Mobile EN 430×932 | `docs/design/screenshots/g1/production/home-mobile-en-430.png` |
| Credits | `docs/design/screenshots/g1/production/credits-en.png` |
| About | `docs/design/screenshots/g1/production/about-en.png` |

Machine-readable QA: `docs/design/screenshots/g1/production/prod-qa.json`

---

## Homepage hero

| Check | Result |
|-------|--------|
| Cinematic backdrop | **PASS** — full-bleed SOULM8TE artwork |
| Gradient / readability | **PASS** |
| Title + metadata | **PASS** — secondary chips readable |
| Play dominant | **PASS** — gold primary |
| More Info secondary | **PASS** |
| Mobile My List compact | **PASS** — `[Play] [More Info] [+]` single row at 390/430 |
| No clipping / giant empty | **PASS** |
| `data-autoplay="false"` | **PASS** |
| Idle 32s watch | **PASS** — slide **never** auto-advanced (Soulm8te → still Soulm8te) |
| Desktop next/prev | **PASS** — next → Shawshank; prev works |
| Dots | **PASS** — subtle active pill |
| Mobile swipe/dots | **PASS** |

---

## Header

| Check | Result |
|-------|--------|
| Transparent over hero | **PASS** |
| Scroll dark/blur | **PASS** (style change on scroll) |
| Nav: Home/Movies/Series/Children/Genres/More | **PASS** |
| More menu items | **PASS** — Collections, What to Watch, Dubbed, Subtitled, New Releases, Request Movie |
| Notifications icon | **PASS** — absent |

---

## Media cards

| Check | Result |
|-------|--------|
| Real catalog artwork | **PASS** |
| Poster 2:3 | **PASS** — img 220×330 (ratio 1.5) |
| Premium desktop size | **PASS** — ~220px wide cards |
| No stretched posters | **PASS** |
| Title controlled | **PASS** |
| Overlay actions | Play / My List / Details (restrained) |
| No hover trailer autoplay | **PASS** |

---

## Continue Watching

Authenticated QA subscriber JWT:

| Check | Result |
|-------|--------|
| Section visible | **PASS** |
| S/E context | **PASS** — episode sample `S1 · E1` |
| Progress API | **PASS** — episode 75.56%, movie 45% |
| Watchlist API | **PASS** (200) |
| Anon My List → `/login` | **PASS** |

---

## Mobile (390 / 430)

| Check | Result |
|-------|--------|
| CTA row single band | **PASS** |
| Bottom nav Home/Movies/Series/Search/Profile | **PASS** (EN + FA/PS labels) |
| Safe-area / no content hide | **PASS** |
| Footer height | **PASS** — compact (~not a giant wall); accordion grouping |
| Horizontal overflow | **PASS** — none |

---

## Branding + TMDB

| Check | Result |
|-------|--------|
| Customer brand | **iFilm by Haroon Net** |
| Footer / copyright / meta | **PASS** |
| About copy | **PASS** — Haroon Net |
| Customer-facing Mobin Net | **PASS** — absent |
| Footer TMDB prominent | **PASS** — absent; Credits link only |
| Credits page TMDB attribution | **PASS** |

Internal `mobinnet.af` URLs (where present) left unchanged as technical/contact endpoints.

---

## RTL (FA / PS)

| Surface | Result |
|---------|--------|
| Header / logo / tools | **PASS** mirrored |
| Hero text + CTA order | **PASS** — Play toward start edge |
| Section headings | **PASS** right-aligned |
| Cards / shelves | **PASS** |
| Bottom nav | **PASS** labels fit |
| Language menu | **PASS** |
| Player | not redesigned; remains LTR contract |

---

## Performance (v1.15.0 vs v1.14.3)

| Metric | v1.14.3 | v1.15.0 | Delta |
|--------|---------|---------|-------|
| Main customer JS raw | 311,046 | 317,156 | **+6.1 KB (~2%)** |
| Main customer JS gzip | 97,714 | 99,538 | **+1.8 KB (~1.9%)** |
| Homepage API calls (browser) | config + home | config + home | stable (2) |
| Home API latency (origin) | — | ~189 ms / 164 KB | ok |
| Desktop FCP (Playwright) | — | ~1120 ms | ok |
| Mobile Fast3G LCP (approx) | — | ~3384 ms | ok |
| Hero artwork requests | — | backdrop + logo (+ shelf posters) | idle prefetch only |

Homepage DB query count: **not measured** — `pg_stat_statements` requires `shared_preload_libraries` (postgres restart); deferred to avoid production disruption. No backend code changed in this release.

**Verdict:** no meaningful performance regression for a visual minor.

---

## Functional regression

| Area | Result |
|------|--------|
| Movies / Series / Search / Request pages | **PASS** (200, not 404) |
| Playback session + master.m3u8 | **PASS** (201 + stream 200) on movie 39 |
| Watchlist | **PASS** |
| Continue Watching | **PASS** |
| Recommendations API | **PASS** (200) |
| Search API | **PASS** (200) |
| Localization EN/FA/PS | **PASS** |
| Protected streaming path | **PASS** |

---

## Remaining visual findings

None **BLOCKER** / **HIGH**.

Non-blocking notes:

1. Desktop My List still uses full label (by design); mobile uses compact `+`.
2. `/about` and `/credits` share the About + attribution section in the current legal page structure — TMDB attribution remains on Credits as required.
3. Footer social/website destinations may still point at existing `mobinnet.af` hosts (technical URLs, not customer brand copy).

---

## Gate

| Gate | Status |
|------|--------|
| Merge + signed release | ✓ |
| update-agent deploy | ✓ |
| version 1.15.0 / migration 023 | ✓ |
| verify-installation | ✓ |
| digests aligned / rollback 1.14.3 | ✓ |
| Hero cinematic + manual-only | ✓ |
| Mobile CTA density | ✓ |
| Haroon Net branding | ✓ |
| Credits/TMDB | ✓ |
| RTL FA/PS | ✓ |
| Perf preserved (~2% JS) | ✓ |
| Functional smoke | ✓ |
| No BLOCKER / HIGH | ✓ |

**STOP after G1.** Do **not** automatically begin G2 (Movie/Series Detail V2). Await human review of the live production GUI.

---

*End of G1_PRODUCTION_VERIFICATION.md*
