# Watchlist + Continue Watching improvements

**Status:** Implementation in progress (PR #49)  
**Branch:** `cursor/watchlist-continue-watching-4873`  
**Baseline:** main @ v1.7.0 (Collections V1)  
**Migration tip:** `017_watchlist_v1` (revises `016_collections_v1`)

## Goal

Ship subscriber Watchlist CRUD and improve Continue Watching UX without bundling Recommendations or Collections work.

## Explicitly out of scope

- Recommendations / “What to Watch”
- Collections changes (already in v1.7.0)
- Movie Detail Experience (separate PR #50 track)
- Content requests
- Analytics platform / behavioral ranking beyond resume ordering
- DRM / CDN / offline / Cast receiver

## Delivered in this track

### Watchlist API

- `GET /api/me/watchlist`
- `GET /api/me/watchlist/membership`
- `POST /api/me/watchlist` — movie **or** series (XOR)
- `DELETE /api/me/watchlist/{id}`
- `DELETE /api/me/watchlist` — clear all, or remove by `movie_id` / `series_id`
- Auth: subscriber only; admins 403; anonymous 401
- Duplicate membership → 409
- Unpublished titles → unavailable tombstones (no poster/path leakage)
- Deleting watchlist rows never deletes movies/series

### Schema

Migration `017_watchlist_v1`:

- Reshapes `watchlist_items` to `movie_id` XOR `series_id` with FKs + partial uniques
- Adds `user_watch_progress.hidden_from_continue` for dismiss-without-delete

### Continue Watching

- Homepage shelf: authenticated + non-empty only (unchanged)
- Filters: incomplete, `position ≥ 30s`, not hidden, published + playable
- `DELETE /api/me/continue-watching/{asset_id}` dismisses from shelf; history retained
- Resume progress clears dismiss so the title can return

### Customer UI

- Watchlist toggle on movie + series detail
- `/watchlist` grid with remove + clear all
- Desktop nav **My List**
- Continue Watching dismiss control on homepage cards
- en / fa / ps via existing i18n keys

## Non-goals for first merge

- Recommendation ranking of watchlist
- Shared/family watchlists
- Push notifications
- “Because you watched” shelves

## Release notes stub (future)

Cut a **separate** release after Ready — do not back-port into v1.7.0.
