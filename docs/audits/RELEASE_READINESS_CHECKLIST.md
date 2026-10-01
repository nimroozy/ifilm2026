# iFilm release readiness checklist

**Date:** 2026-10-01  
**Baseline main:** `5adb6d47889f9ed8fb1e825d7b83144461a58855`  
**Latest stable release:** `v1.19.0` → `42ff05dd06ed2a0c8675dac0d1ea329d6f4e5281`  
**Live site:** https://ifilm.af (deploy ≠ main tip; host was updated to v1.19.0 on 2026-08-21)  
**Historical roadmap:** PR #65 (v1.14.2 audit) — historical only  

Status keys: **main** | **draft PR** | **tests** | **browser/staging** | **production** | **missing/blocked**

---

## Customer navigation and GUI

| Item | Status | Evidence |
|------|--------|----------|
| Document titles (customer + player) | main (#94) | #79 `CustomerDocumentTitle` + player title; merged via #94 |
| Homepage h1 when hero uses logo image | main (#94) | #79 `HeroCarousel` sr-only `h1` |
| Desktop/mobile nav + `aria-current` | main (#94) | `CustomerLayout.tsx` active states; #80 touch/RTL polish |
| Keyboard focus / button labels | main (#94) | #79/#80 a11y labels on hero, browse filters, cards |
| Duplicate Recently Added / New Releases | main (#94) | #80 `Index.tsx` `recHasNewReleases` gate |
| Empty shelves omitted | main (#94) | `ContentRow` returns null when empty |
| Manual-only hero | main + real-backend QA | Hero interactions assert no auto-advance |
| EN/FA/PS + RTL shell; player LTR | main (#94) | translations + `VideoPlayer`/`PlayerControls` `dir="ltr"` |
| Browse clear-filters / labeled controls | main (#94) | #80 `moviesBrowseA11y.test.tsx` |
| Production CSP + font loading | main (#94) | `index.html` stylesheet links without inline `onload` (CSP `script-src 'self'`) |
| Coming Soon / Unavailable UI labels | main (#94) | Routed through translations (hero/movie/browse); EN/FA/PS unit tests |
| RTL hero synopsis grouping | main (#94) | `text-start` block + `dir=auto` isolate inner span |

## Movie and series detail

| Item | Status | Evidence |
|------|--------|----------|
| Movie detail muted trailer + reduced-motion | main | `MovieDetailView.tsx` (preserved; #80 minor a11y) |
| Series trailer manual button | main | series detail path |
| Mobile detail readability after entrance settle | real-backend QA | Harness waits for finite entrance animations + opacity≥0.999; before/after in `review/` |
| Production browser QA of GUI (#94 on main) | pending | Merged into main; production verification still pending (no release/deploy) |

## Search and filtering

| Item | Status | Evidence |
|------|--------|----------|
| Search UI + empty/error/retry | main + draft | `Browse.tsx` SearchPage; retry localized on GUI branch |
| Typed vs URL query | main | movies genre URL sync; search local state |
| End-to-end API search on GUI tip | real-backend QA | empty + results + clear; bottom-nav clearance |

## Login, sessions, entitlement, devices

| Item | Status | Evidence |
|------|--------|----------|
| Portal auth contract | main | subscriber/portal routes + docs |
| Device limits / cross-user isolation | main (code) | backend tests exist; production verified separately historically |
| GUI tip auth E2E (local disposable) | PASS (LOCAL) | Disposable Portal Voice AI stub + fixture users — **not** live Portal proof |
| Live Portal QA | NOT RUN | No production Portal credentials this session |

## Playback, resume, audio, subtitles, casting

| Item | Status | Evidence |
|------|--------|----------|
| Protected streaming | main / production v1.19.0 | stream 401 unauth smoke historically |
| Player LTR controls | main + LOCAL QA | FA player `dir=ltr` on player/controls/seek |
| Playback advances + resume proof on GUI tip | PASS (LOCAL) | Disposable packaged HLS for movie/3; advance past min seconds; resume near saved; Start Over ~0 |

## Watchlist / Continue Watching / Recommendations / Content Requests

| Item | Status | Evidence |
|------|--------|----------|
| Features in main | main | APIs + pages + unit tests |
| GUI tip browser proof (My List persistence) | PASS (LOCAL) | Add movie+series → reload → remove → reload; second account isolated |

## Admin content / artwork / media

| Item | Status | Evidence |
|------|--------|----------|
| Admin CMS / media pipeline | main | upload→probe→package→publish |
| Artwork upload in editors | partial / missing polish | URL fields; file upload to ARTWORK_ROOT incomplete as productized flow |
| Disposable representative fixtures | LOCAL QA | Seeded artwork + packages in `ifilm_gui_qa`; missing-artwork case retained |

## Portal settings

| Item | Status | Evidence |
|------|--------|----------|
| Admin Portal settings page | main | `PortalSettingsPage.tsx` |

## R2 / storage settings

| Item | Status | Evidence |
|------|--------|----------|
| Admin Storage / CDN settings | draft (R2 integration) | `StorageSettingsPage` at `/admin/settings/storage`; `/settings/r2` redirects |
| Artwork CDN publish + local fallback | draft (R2 integration) | Reuses #92 tip `bdd4ede5…` on `cursor/r2-artwork-storage-integration-4873` |
| PR #93 Storage/CDN ops UI | draft #93 | Keep separate; do not merge; no migration 030; no Debian provisioning |

## CDN provisioning / routing / monitoring

| Item | Status | Evidence |
|------|--------|----------|
| CDN management control plane | main (#91) + draft #93 P1 | `managed_cdn_nodes`, encrypted creds |
| Real Debian 13 provision proof | blocked | No authorized disposable host this session |
| Flags | production OFF | `ENABLE_CDN_SYNC=false`; edge routing stays off |

## Performance

| Item | Status | Evidence |
|------|--------|----------|
| Aggregated home APIs / budgets | main | frontend CI bundle budget |
| Fresh N+1 measurement this tip | missing | Not in GUI milestone |

## Release / backup / rollback

| Item | Status | Evidence |
|------|--------|----------|
| Signed release + update-agent | main / production | v1.19.0 published; host update path proven historically |
| GUI #94 release / production deploy | pending | Merged to main; no tag/deploy yet |

---

## Open PRs reused / preserved

| PR | Head | Role |
|----|------|------|
| #79 | `17c56899…` | GUI a11y + titles — **superseded/closed** via #94 (branch retained) |
| #80 | `f08be9aa…` | i18n/a11y/homepage rails — **superseded/closed** via #94 (branch retained) |
| #92 | `bdd4ede5…` | R2 artwork CDN — source for R2 integration branch (do not force-push) |
| #93 | `2003a5cc…` | CDN-P1 — keep separate / Draft (do not merge) |
| #81–#89 | stacked CDN | Ancestry in main via #90; do not re-merge |
| #65 | audit docs | Historical roadmap only |
| #67 | T0 docs | Do not use as implementation base |

## GUI integration branch

- Branch: `cursor/gui-stabilization-4873`
- PR: **#94 MERGED** into `main` @ `9d7f81be50a601e539608c23e7b45e9b8a9c5d0b` (approved tip `906de02d…`)
- PRs #79 / #80: closed as superseded by #94 (branches retained)
- Production verification of GUI tip: **still pending** (no release/deploy from this merge)
- Alembic head on main: **029** (do not import #93 migration 030 here)

---

## Verification layers (do not conflate)

### 1) Automated component / unit tests

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm run lint` / `typecheck` / `test` / `build` | PASS locally on tip | 265 tests; API-mode build + secret scan + bundle budget OK |
| `scan:build-secrets` / `check:bundle-budget` | PASS locally | Frontend CI must match final head |

### 2) Mock visual QA (`VITE_DATA_MODE=mock`)

| Check | Result | Notes |
|-------|--------|-------|
| Mock preview visual captures | PASS (historical this branch) | Artifacts: `/opt/cursor/artifacts/gui-*.png`, `/opt/cursor/artifacts/gui-mock-qa/` |
| Data source | mock fixtures | **Not** real-backend proof; keep labeled separately |

### 3) Real-backend browser QA (`VITE_DATA_MODE=api`)

| Check | Result | Notes |
|-------|--------|-------|
| Harness | PASS | `gui-stabilization-screenshots.mjs` — 84/84; shared `finalizeCase`; entrance settle; decoded artwork or intentional fallback |
| Environment | disposable local | Isolated DB `ifilm_gui_qa`, alembic **029**, production CSP, API dist |
| `/api/config` | PASS | 200 |
| Catalog from real backend | PASS | Featured/home/movies/series from Postgres; representative + fallback fixtures |
| Home/browse matrix 1920–390 × EN/FA/PS | PASS | Locale `ifilm.locale`; EN=LTR, FA/PS=RTL |
| Hero manual arrows / no auto-advance | PASS | Interaction case |
| Movies filter + clear; search empty/results; retry recovery | PASS | |
| Movie/series detail mobile + desktop | PASS | opacity settled; motion + reduced-motion pairs |
| Unexpected first-party errors | 0 | CSP intact; intentional retry abort filtered |
| Review screenshots | `/opt/cursor/artifacts/gui-api-qa/review/` | `before/` + `after/` + `summary.json` + `findings.json` |

### 4) Local test-account authenticated GUI

| Check | Result | Notes |
|-------|--------|-------|
| Login / refresh session / logout | PASS | Label: **local disposable Portal Voice AI stub** + fixture user `mobin_user_001` |
| Live Portal authentication | NOT RUN | Stub token is not a production Portal credential |

### 5) Local test-account playback / resume

| Check | Result | Notes |
|-------|--------|-------|
| Playback currentTime advances | PASS (LOCAL) | Packaged HLS via existing media workflow; not manually marked playable |
| Resume near saved position | PASS (LOCAL) | After threshold; resume dialog/position within margin |
| Start Over from beginning | PASS (LOCAL) | |
| Player LTR under FA/PS | PASS (LOCAL) | |
| Live Portal / production playback | NOT RUN | Out of scope |

### 6) Live Portal QA / production verification

| Check | Result | Notes |
|-------|--------|-------|
| Live Portal | NOT RUN | Out of scope for this GUI validation pass |
| Production deploy of this tip | NOT RUN | Draft PR only; historical production evidence is **not** current tip verification |

---

## Visual review findings (PR #94)

| # | Root cause | Fix type | Test | Remaining limitation |
|---|------------|----------|------|----------------------|
| 1 Mobile detail dim | Capture during `animate-fade-in` | Harness settle (opacity≥0.999 + anim done); no global opacity overrides | motion/reduced detail cases | Human visual approval still required |
| 2 Availability labels | Hard-coded EN in helpers / hero | App: translated labels at call sites | unit EN/FA/PS | EN catalog metadata fallback intentional |
| 3 RTL hero grouping | `dir=auto` on synopsis block | App: `text-start` + isolate inner span | hero unit + rtl_hero harness | Mixed-script titles still rely on unicode bidi |
| 4 Representative fixtures | Incomplete-content-only shots | Disposable seed + richer local artwork; keep fallbacks | populated + missing-artwork | Local artwork/packages only; not CDN |
| 5 Watchlist + playback | Missing packages / identity-mode mismatch for portal subjects | LOCAL seed + `SUBSCRIBER_IDENTITY_MODE=portal` for stub QA | watchlist + playback cases | LOCAL stub ≠ live Portal |
| 6 Shared finalizer | Detail cases could skip collectors | Shared `finalizeCase` + http404 URLs | full harness 84 | — |
| 7 Search / mobile nav | Bounded polish request | Clear/empty/results + bottom clearance | search + clearance cases | No search backend redesign |

---

## Browser QA artifacts

- **Real-API run:** `/opt/cursor/artifacts/gui-api-qa/` (+ `review/before`, `review/after`, `summary.json`, `findings.json`)
- **Mock visual (separate label):** `/opt/cursor/artifacts/gui-*.png`, `/opt/cursor/artifacts/gui-mock-qa/`
- Do not overwrite mock captures and relabel them as real-API verification.
