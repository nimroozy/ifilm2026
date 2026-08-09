# G2b — Series Detail V2 Production Verification

**Status:** LIVE VERIFIED — returned for human review  
**Site:** https://ifilm.af  
**Release:** `v1.17.0`  
**Do not start G3 / T1 / player redesign.**

---

## Merge / release chain

| Step | Result |
|------|--------|
| Planning PR #74 (docs-only) | Squash-merged to `main` as `04e84c7d…` |
| Implementation PR #75 | Rebased onto main; CI green; marked Ready; squash-merged as `925c9c434f07e90d6d6d2012c9057157506f8a38` |
| Tag | `v1.17.0` → commit `925c9c434f07e90d6d6d2012c9057157506f8a38` |
| Release workflow | https://github.com/nimroozy/ifilm2026/actions/runs/31324196871 — **quality PASS**, **publish PASS** |
| GitHub Release | https://github.com/nimroozy/ifilm2026/releases/tag/v1.17.0 |

### Release artifacts present

- `release-manifest.json` + `.sig` (signed)
- `SHA256SUMS`
- `ifilm-1.17.0.tar.gz`
- SBOMs (`ifilm-1.17.0-backend.sbom.spdx.json`, `ifilm-1.17.0-frontend.sbom.spdx.json`)
- Trivy JSON reports
- Updater-compatible image digests in manifest

---

## Deploy

| Field | Value |
|-------|-------|
| Workflow | `update-agent` → `install_verified_release` (stable channel) |
| Installed version | **1.17.0** |
| Commit | `925c9c434f07e90d6d6d2012c9057157506f8a38` |
| Migration head | **023_media_tracks_packaging_v1** (no new migration) |
| Rollback target | **1.16.0** |
| Channel | stable |
| `verify-installation` | **ok** / healthy |
| Backend digest | `sha256:b169429df80f02c5922077e3f2d7e355ed298f4414165d50cb96e51cb411b48e` |
| Frontend digest | `sha256:10659504e2b46ade89b20179c25cec30a8a62d82805c06dc7061b574393c5b41` |
| Digests aligned | manifest = env = compose = running |

Evidence: `/opt/cursor/artifacts/v1170-prod/deploy-install.log`, `verify-installation` agent output.

---

## Real series credits (REQUIRED — LIVE)

Existing pipeline only: `POST /api/admin/tools/tmdb/refresh-title`  
Body: `{ "media_type": "series", "entity_id": <id> }`  
No second sync mechanism. Credentials not logged.

| Series | Refresh HTTP | credits_count | Detail credits | credits_synced_at | Cast UI |
|--------|-------------:|--------------:|---------------:|-------------------|--------|
| Game of Thrones (`/series/4`) | 200 | 14 | **14** | `2026-08-09T16:51:03.680193Z` | **LIVE** — portraits + names/characters |
| Breaking Bad (`/series/8`) | 200 | 8 | **8** | `2026-08-09T16:51:04.913345Z` | API populated |

Sample GoT credits (LIVE API): Peter Dinklage / Tyrion; Kit Harington / Jon Snow; Emilia Clarke / Daenerys — profiles present.

Evidence: `/opt/cursor/artifacts/v1170-prod/credits-refresh-summary.json`, screenshot `prod-series-desktop-1440-en-cast.png`.

**Distinction:** Pre-merge injection was component QA only. Production cast above is **REAL verified** after TMDB refresh.

---

## Hero (LIVE)

| Check | Result |
|-------|--------|
| Cinematic backdrop | PASS |
| Scrims / logo title | PASS (GoT logo) |
| Metadata / overview | PASS (`2011–2019`, genres, rating) |
| One primary CTA | PASS — Continue Watching S01E02 44% |
| My List + Trailer secondary | PASS |
| Trailer policy | `button-only` |
| Wait ≥15s, no auto trailer | **PASS** (`hero_mode=backdrop`, no embed) |
| Manual trailer open | PASS |

---

## CTA state machine

| State | Evidence class | Result |
|-------|----------------|--------|
| Continue Watching S01E02 44% | **LIVE** (QA subscriber history) | PASS — exclusive primary |
| Next Episode (same season) | **LIVE possible** (S01E01→S01E02 playable) | Catalog supports; Continue shown for incomplete |
| Next Episode (season boundary S01E10→S02E01) | **UNIT/INTEGRATION** | Accepted — GoT S02 not playable; do not manufacture catalog |
| Watch Again | UNIT/INTEGRATION | Covered pre-merge |
| Play (no progress) | UNIT/INTEGRATION | Covered pre-merge |

No multiple primary CTAs observed live.

---

## Continue Watching (LIVE)

- Episode: S01E02 The Kingsroad  
- Progress: **44%** (history + CTA + row Resume bar)  
- Routes to correct series episode player path  
- No cross-series leakage observed on GoT detail  
- Player unchanged / LTR

---

## Season selector / mobile sheet (LIVE)

| Surface | Result |
|---------|--------|
| Desktop compact selector | PASS (`Season 1 · 3 Episodes`) |
| Mobile bottom sheet 390×844 | PASS — selected season clear, large targets, close works |
| Mobile 430×932 | PASS (page load) |
| RTL sheet/selector | PASS (FA desktop + mobile) |

---

## Season-scoped network (LIVE)

Initial authenticated open approximately:

- `/api/series/4`
- `/api/series/4/seasons`
- `/api/series/4/episodes?season=…`
- recommendations
- CW / history / watchlist / entitlement

**Not** a full dump of every season for large catalogs. Implementation prefetches **selected season + next season** for Next-CTA resolution. GoT has only two seasons, so both appear. Changing to an already-prefetched season uses cache (no extra request observed).

---

## Episode rows (LIVE)

- 16:9 thumbs, `SxxExx`, titles, durations  
- Description clamp, Resume / Unavailable states  
- Progress bar on S01E02  
- No stretched thumbs / empty technical fields observed  

---

## Episode SQL performance

Regression tests remain green in release tree:

| Episodes | SQL statements |
|---------:|---------------:|
| 3 | 6 |
| 10 | 6 |
| 20 | 6 |

`tests/test_series_episode_list_query_counts.py` — **PASS** (local on `main` / release SHA).

---

## Browse / list credits safety (LIVE)

- `GET /api/series` browse loads normally  
- List items may include empty `credits: []` field but **no nonempty cast payloads**  
- Cast rail / nonempty credits only on detail after refresh  
- Query-ceiling tests green in release code  

---

## More Like This (LIVE)

- Shelf visible on GoT detail  
- Series-oriented recommendations (Arcane, Mandalorian, Breaking Bad, …)  
- Current title not observed as self-duplicate in shelf sample  

---

## RTL / localization (LIVE)

| Locale | Desktop | Mobile | dir |
|--------|---------|--------|-----|
| EN | PASS | PASS | ltr |
| FA | PASS | PASS | rtl |
| PS | PASS | PASS | rtl |

Player remains LTR (unchanged). PS fallback policy unchanged (English, never Persian).

---

## G2a regression (LIVE)

Soulm8te `/movie/31`:

| Check | Result |
|-------|--------|
| Movie Detail loads | PASS |
| Cast rail | PASS |
| CTA Continue Watching | PASS |
| Trailer after ~6–7s | PASS (`hero_mode` backdrop → trailer, embed present) |
| Series button-only trailer unchanged | PASS (separate surface) |

---

## Performance

| Metric | Result |
|--------|--------|
| Customer initial JS (local build gate) | ~692 KB raw — within 800 KB fail budget |
| Live initial JS assets | `index-*.js`, react/query/router/http vendors |
| Series Detail open | interactive; no G1/G2a-style regression observed |
| Selected-season episode API | season-scoped queries |

---

## Screenshots (live ifilm.af)

Under `docs/design/screenshots/g2b-prod/` and `/opt/cursor/artifacts/v1170-prod/shots/`:

- `prod-series-desktop-1920-en.png`
- `prod-series-desktop-1440-en.png`
- `prod-series-desktop-1440-en-continue.png`
- `prod-series-desktop-1440-en-trailer.png`
- `prod-series-desktop-1440-en-episodes.png`
- `prod-series-desktop-1440-en-cast.png` (**REAL** cast after TMDB refresh)
- `prod-series-desktop-1440-en-recs.png`
- `prod-series-desktop-1440-fa.png`
- `prod-series-desktop-1440-ps.png`
- `prod-series-mobile-430-en.png`
- `prod-series-mobile-390-en.png`
- `prod-series-mobile-390-en-season-sheet.png`
- `prod-series-mobile-390-fa.png`
- `prod-series-mobile-390-ps.png`
- `prod-g2a-movie-desktop-1440-en-trailer.png`

---

## Remaining findings (non-blocking)

| Level | Finding | Class |
|-------|---------|-------|
| LOW | Season label pluralization (`2 Season`) | Accepted follow-up |
| INFO | Trailer may wrap under My List on narrow widths | Accepted |
| INFO | Selected+next season prefetch for CTA (not all seasons) | By design |
| — | Season-boundary Next | **UNIT/INTEGRATION verified**, not live (S02 unplayable) |

No BLOCKER / HIGH for production G2b.

---

## Evidence classes summary

| Area | Class |
|------|-------|
| Deploy / digests / migration / health | **REAL verified** |
| TMDB credits refresh + cast rail | **REAL verified** |
| Continue Watching CTA / progress | **REAL verified** |
| Trailer button-only (15s) | **REAL verified** |
| Season UI + mobile sheet | **REAL verified** |
| RTL FA/PS | **REAL verified** |
| G2a 6s movie trailer | **REAL verified** |
| Browse without cast payloads | **REAL verified** |
| Episode SQL ceiling 6/6/6 | **UNIT/INTEGRATION verified** (release tests) |
| Season-boundary Next | **UNIT/INTEGRATION verified** |

---

## Stop

`v1.17.0` is live on https://ifilm.af with G2b Series Detail V2 verified.

**Do not start G3. Do not start T1. Do not start player redesign.**

Await human review of this production result.
