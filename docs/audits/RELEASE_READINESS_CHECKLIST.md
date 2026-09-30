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
| Manual-only hero | main | Hero data from featured catalog; no auto-editorial hero swap in #79/#80 |
| EN/FA/PS + RTL shell; player LTR | main + draft | translations + `VideoPlayer`/`PlayerControls` `dir="ltr"` |
| Browse clear-filters / labeled controls | draft PR | #80 `moviesBrowseA11y.test.tsx` |

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
| End-to-end API search on GUI tip | browser TBD | Unit tests mock; live browser after preview |

## Login, sessions, entitlement, devices

| Item | Status | Evidence |
|------|--------|----------|
| Portal auth contract | main | subscriber/portal routes + docs |
| Device limits / cross-user isolation | main (code) | backend tests exist; production verified separately historically |
| GUI tip auth E2E | missing this session | Needs authorized test account |

## Playback, resume, audio, subtitles, casting

| Item | Status | Evidence |
|------|--------|----------|
| Protected streaming | main / production v1.19.0 | stream 401 unauth smoke historically |
| Player LTR controls | main | player tests |
| Playback advances + resume proof on GUI tip | missing | NOT RUN this session without test media account |

## Watchlist / Continue Watching / Recommendations / Content Requests

| Item | Status | Evidence |
|------|--------|----------|
| Features in main | main | APIs + pages + unit tests |
| GUI tip browser proof | missing | Preview/browser after start |

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
| Artwork CDN publish | draft #92 | `ENABLE_ARTWORK_CDN_SYNC`; known Ruff F841 in tests at reviewed head |
| StorageSettingsPage redirect | draft #93 | Must reconcile with #92 controls before merge |

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
| #79 | `17c56899…` | GUI a11y + titles — **cherry-picked** into GUI branch |
| #80 | `f08be9aa…` | i18n/a11y/homepage rails — **cherry-picked** into GUI branch |
| #92 | `bdd4ede5…` | R2 artwork CDN — keep separate |
| #93 | `2003a5cc…` | CDN-P1 — keep separate / Draft |
| #81–#89 | stacked CDN | Ancestry in main via #90; do not re-merge |
| #65 | audit docs | Historical roadmap only |
| #67 | T0 docs | Do not use as implementation base |

## GUI integration branch

- Branch: `cursor/gui-stabilization-4873`
- Base: `origin/main` @ `5adb6d47…`
- Reused commits (cherry-pick order): `f08be9aa` (#80), then `17c56899` (#79)
- Follow-up commit(s): localized retry/load-failed strings on home/browse/search

## Browser QA (this session)

| Check | Result | Notes |
|-------|--------|-------|
| Mock preview (`VITE_DATA_MODE=mock`) | PASS | Rebuild + preview on `:4173` |
| EN/FA/PS home + RTL | PASS | FA/PS `dir=rtl`; nav labels localized |
| Movies mobile 390 + tablet 768 | PASS | Grid, filters, active bottom nav |
| Search desktop | PASS | Popular searches + titled doc |
| Movie/series detail titles | PASS | `Movie · iFilm` / `Series · iFilm` |
| Horizontal overflow | PASS | 0 overflow across captured set |
| Auth/watchlist/playback advance | NOT RUN | No authorized test account/media this session |
| Production visual of this tip | NOT RUN | Tip not deployed |

Artifacts under `/opt/cursor/artifacts/gui-*.png` and `gui-stabilization/`.
Preview console still shows `/api/config` 500 on static preview (expected without backend); catalog uses mock fixtures.
