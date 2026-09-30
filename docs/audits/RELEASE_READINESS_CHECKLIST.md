# iFilm release readiness checklist

**Date:** 2026-09-30  
**Baseline main:** `5adb6d47889f9ed8fb1e825d7b83144461a58855`  
**Latest stable release:** `v1.19.0` → `42ff05dd06ed2a0c8675dac0d1ea329d6f4e5281`  
**Live site:** https://ifilm.af (deploy ≠ main tip; host was updated to v1.19.0 on 2026-08-21)  
**Historical roadmap:** PR #65 (v1.14.2 audit) — historical only  

Status keys: **main** | **draft PR** | **tests** | **browser/staging** | **production** | **missing/blocked**

---

## Customer navigation and GUI

| Item | Status | Evidence |
|------|--------|----------|
| Document titles (customer + player) | draft PR (GUI integration) | #79 `CustomerDocumentTitle` + player title; integrated on `cursor/gui-stabilization-4873` |
| Homepage h1 when hero uses logo image | draft PR | #79 `HeroCarousel` sr-only `h1` |
| Desktop/mobile nav + `aria-current` | main + draft polish | `CustomerLayout.tsx` active states; #80 touch/RTL polish |
| Keyboard focus / button labels | draft PR | #79/#80 a11y labels on hero, browse filters, cards |
| Duplicate Recently Added / New Releases | draft PR | #80 `Index.tsx` `recHasNewReleases` gate |
| Empty shelves omitted | main + draft | `ContentRow` returns null when empty |
| Manual-only hero | main + real-backend QA | Hero interactions assert no auto-advance |
| EN/FA/PS + RTL shell; player LTR | main + draft | translations + `VideoPlayer`/`PlayerControls` `dir="ltr"` |
| Browse clear-filters / labeled controls | draft PR | #80 `moviesBrowseA11y.test.tsx` |
| Production CSP + font loading | draft PR | `index.html` stylesheet links without inline `onload` (CSP `script-src 'self'`) |

## Movie and series detail

| Item | Status | Evidence |
|------|--------|----------|
| Movie detail muted trailer + reduced-motion | main | `MovieDetailView.tsx` (preserved; #80 minor a11y) |
| Series trailer manual button | main | series detail path |
| Production browser QA of this GUI tip | missing | Not on production until merge+release |

## Search and filtering

| Item | Status | Evidence |
|------|--------|----------|
| Search UI + empty/error/retry | main + draft | `Browse.tsx` SearchPage; retry localized on GUI branch |
| Typed vs URL query | main | movies genre URL sync; search local state |
| End-to-end API search on GUI tip | real-backend QA | See verification matrix below |

## Login, sessions, entitlement, devices

| Item | Status | Evidence |
|------|--------|----------|
| Portal auth contract | main | subscriber/portal routes + docs |
| Device limits / cross-user isolation | main (code) | backend tests exist; production verified separately historically |
| GUI tip auth E2E (local disposable) | local test account | Disposable Portal Voice AI stub + fixture user — **not** live Portal proof |
| Live Portal QA | NOT RUN | No production Portal credentials this session |

## Playback, resume, audio, subtitles, casting

| Item | Status | Evidence |
|------|--------|----------|
| Protected streaming | main / production v1.19.0 | stream 401 unauth smoke historically |
| Player LTR controls | main | player tests |
| Playback advances + resume proof on GUI tip | NOT RUN / BLOCKED | Disposable DB has published catalog metadata but **no packaged test media** / streamable packages |

## Watchlist / Continue Watching / Recommendations / Content Requests

| Item | Status | Evidence |
|------|--------|----------|
| Features in main | main | APIs + pages + unit tests |
| GUI tip browser proof (My List persistence) | NOT RUN | Auth smoke covered login/logout/session; watchlist add/remove not exercised with packaged content |

## Admin content / artwork / media

| Item | Status | Evidence |
|------|--------|----------|
| Admin CMS / media pipeline | main | upload→probe→package→publish |
| Artwork upload in editors | partial / missing polish | URL fields; file upload to ARTWORK_ROOT incomplete as productized flow |

## Portal settings

| Item | Status | Evidence |
|------|--------|----------|
| Admin Portal settings page | main | `PortalSettingsPage.tsx` |

## R2 / storage settings

| Item | Status | Evidence |
|------|--------|----------|
| Admin R2 page | main (#91) | `R2SettingsPage` hot tier |
| Artwork CDN publish | draft #92 | Keep separate from GUI PR #94 |
| StorageSettingsPage redirect | draft #93 | Keep separate; do not import migration 030 into GUI branch |

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
| This GUI tip release | missing | Draft PR only; no tag/deploy |

---

## Open PRs reused / preserved

| PR | Head | Role |
|----|------|------|
| #79 | `17c56899…` | GUI a11y + titles — **cherry-picked** into GUI branch (do not close) |
| #80 | `f08be9aa…` | i18n/a11y/homepage rails — **cherry-picked** into GUI branch (do not close) |
| #92 | `bdd4ede5…` | R2 artwork CDN — keep separate |
| #93 | `2003a5cc…` | CDN-P1 — keep separate / Draft |
| #81–#89 | stacked CDN | Ancestry in main via #90; do not re-merge |
| #65 | audit docs | Historical roadmap only |
| #67 | T0 docs | Do not use as implementation base |

## GUI integration branch

- Branch: `cursor/gui-stabilization-4873`
- PR: **#94 DRAFT**
- Base: `origin/main` @ `5adb6d47…`
- Reused commits (cherry-pick order): `f08be9aa` (#80), then `17c56899` (#79)
- Follow-up: localized retry/load-failed strings; CSP-safe fonts; hardened `gui-stabilization-screenshots.mjs`
- Alembic head on this branch: **029** (do not import #93 migration 030)

---

## Verification layers (do not conflate)

### 1) Automated component / unit tests

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm run lint` / `typecheck` / `test` / `build` | see PR Frontend CI on tip | Run from `app/frontend` |
| `scan:build-secrets` / `check:bundle-budget` | required on tip | |

### 2) Mock visual QA (`VITE_DATA_MODE=mock`)

| Check | Result | Notes |
|-------|--------|-------|
| Mock preview visual captures | PASS (historical this branch) | Artifacts: `/opt/cursor/artifacts/gui-*.png`, `/opt/cursor/artifacts/gui-mock-qa/` |
| Data source | mock fixtures | **Not** real-backend proof; keep labeled separately |

### 3) Real-backend browser QA (`VITE_DATA_MODE=api`)

| Check | Result | Notes |
|-------|--------|-------|
| Harness | PASS | `app/frontend/scripts/gui-stabilization-screenshots.mjs` — fails on unexpected page/console/5xx/overflow/wrong locale |
| Environment | disposable local | Isolated DB `ifilm_gui_qa`, alembic **029**, production CSP, API dist |
| `/api/config` | PASS | 200 |
| Catalog from real backend | PASS | Featured/home/movies/series from Postgres; not mock fixtures |
| Home/browse matrix 1920–390 × EN/FA/PS | PASS | Locale `ifilm.locale`; EN=LTR, FA/PS=RTL |
| Hero manual arrows / no auto-advance | PASS | Interaction case |
| Movies filter + clear; search empty/results; retry recovery | PASS | |
| Movie/series detail mobile + desktop | PASS | |
| Unexpected first-party errors | 0 | CSP font `onload` removed so production CSP stays intact |
| Review screenshots | `/opt/cursor/artifacts/gui-api-qa/review/` | Includes `summary.json` with commit + dataMode |

### 4) Local test-account authenticated GUI

| Check | Result | Notes |
|-------|--------|-------|
| Login / refresh session / logout | PASS | Label: **local disposable Portal Voice AI stub** + fixture user `mobin_user_001` |
| Live Portal authentication | NOT RUN | Stub token is not a production Portal credential |

### 5) Local test-account playback / resume

| Check | Result | Notes |
|-------|--------|-------|
| Playback currentTime advances | BLOCKED | No packaged/streamable test media in disposable DB |
| Resume near saved position | BLOCKED | Same prerequisite |
| Player LTR under FA/PS | NOT RUN | Depends on player route with media |

### 6) Live Portal QA / production verification

| Check | Result | Notes |
|-------|--------|-------|
| Live Portal | NOT RUN | Out of scope for this GUI validation pass |
| Production deploy of this tip | NOT RUN | Draft PR only; historical production evidence is **not** current tip verification |

---

## Browser QA artifacts

- **Real-API run:** `/opt/cursor/artifacts/gui-api-qa/` (+ `review/` subset)
- **Mock visual (separate label):** `/opt/cursor/artifacts/gui-*.png`, `/opt/cursor/artifacts/gui-mock-qa/`
- Do not overwrite mock captures and relabel them as real-API verification.
