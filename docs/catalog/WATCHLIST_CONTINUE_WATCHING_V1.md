# Watchlist + Continue Watching improvements

**Status:** Draft planning (post–v1.7.0)  
**Branch:** `cursor/watchlist-continue-watching-4873`  
**Baseline:** main @ v1.7.0 (Collections V1 / migration tip `016_collections_v1`)

## Goal

Ship subscriber Watchlist CRUD and improve Continue Watching UX without bundling Recommendations or Collections work.

## Explicitly out of scope

- Recommendations / “What to Watch”
- Collections changes (already in v1.7.0)
- Content requests
- Analytics platform / behavioral ranking beyond resume ordering
- DRM / CDN / offline / Cast receiver

## Current state

### Watchlist

- Table `watchlist_items` exists (migration `001`).
- No public customer HTTP API for add/remove/list.
- UI: movie details show disabled “Watchlist (soon)”; `/watchlist` deferred empty state (no mock titles).
- See `docs/audits/PRODUCT_UI_MEDIA_PLAYER_AUDIT.md` (B4).

### Continue Watching / Watch History

- Implemented for authenticated subscribers (`JWT typ=subscriber`).
- APIs under `/api/me/*` — see `docs/user/WATCH_HISTORY.md`.
- Migration: `009_watch_history`.
- Known gaps: homepage Continue Watching shelf quality, empty/unavailable UX, cross-device polish, and alignment with real catalog playability rules.

## Planned work (this PR track)

### 1. Watchlist API (customer)

- `GET /api/me/watchlist` — ordered list; published + playable preferred; unavailable tombstones
- `POST /api/me/watchlist` — add movie **or** series (XOR ownership)
- `DELETE /api/me/watchlist/{id}` — remove one
- `DELETE /api/me/watchlist` — clear all
- Auth: subscriber only; admins 403; anonymous 401
- Idempotent add; duplicate membership → 409
- Never cascade delete into movies/series
- No admin notes / storage internals / audit leakage in public shapes

### 2. Schema / migration (if needed)

- Inspect `watchlist_items` vs product needs (movie XOR series, unique membership, timestamps).
- Prefer additive migration after `016_collections_v1` only if the existing table is insufficient.
- Preserve catalog integrity; demo seed ownership if demo rows are introduced.

### 3. Customer UI

- Enable Watchlist action on movie/series detail (replace “soon”).
- `/watchlist` real data: grid, empty state, remove, clear.
- Nav entry active when on watchlist routes.
- en / fa / ps + RTL/LTR; no overflow on mobile.
- Unsaved-state N/A for simple toggles; toast/error feedback required.

### 4. Continue Watching improvements

- Homepage shelf: show when authenticated + visible items exist; hide when empty.
- Exclude unpublished, archived, unplayable (no active package) — same rules as `docs/user/WATCH_HISTORY.md`.
- Deterministic ordering (`last_watched_at` desc); bounded query count (no N+1).
- Resume deep-link preserves progress margins.
- Tombstones for unavailable history items; remove-from-CW if product allows without deleting history (document choice).
- Keep existing progress save cadence and completion thresholds unless tests prove a bug.

### 5. RBAC / privacy

- Subscriber-owned only; no public listing endpoints.
- No admin browse of other users’ watchlists in this phase.
- Audit: optional lightweight events for clear-all; avoid noisy per-toggle audit unless existing patterns require it.

### 6. Tests & QA

- Backend: CRUD, XOR, duplicates, authz, visibility, query bounds.
- Frontend: unit + Playwright (desktop/mobile, RTL fa/ps).
- Confirm Collections homepage shelves and routes unchanged.

## Non-goals for first merge of this track

- Recommendation ranking of watchlist
- Shared/family watchlists
- Push notifications
- “Because you watched” shelves

## Release notes stub (future)

After this track is Ready and merged, cut a **separate** release from Collections (v1.7.0). Do not back-port into v1.7.0.

## Rollout checklist (future release)

- Migration tip advances only if a new revision is required
- Updater digest alignment
- Catalog + packages preserved
- Existing `/api/me/continue-watching` and `/api/me/watch-history` contracts remain compatible
- Watchlist visible for subscribers; old routes unchanged
