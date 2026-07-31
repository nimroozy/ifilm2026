# Phase 10 — Watch History Audit

**Date:** 2026-07-31  
**Base:** `main` @ `fbdebe8ddbf476113d13365a4b9335f34b235ab5` (Phase 9 squash)  
**Branch:** `user/watch-history`  
**Alembic head before Phase 10:** `008_publishing_workflow`

---

## Identity findings

| Question | Finding |
| --- | --- |
| Real subscriber identity? | **Yes** — `Subscriber` integer PK; JWT `typ=subscriber`, `sub=<id>` after Radius (or mock Radius) login |
| Admin identity? | Separate `AdminUser` JWT `typ=admin` |
| Playback sessions tied to principal? | Yes — `principal_type` + `principal_id` (string) on `MediaPlaybackSession`; no FK |
| Admin playback → history? | **No** — operational only; history APIs require subscriber |
| Anonymous progress? | **Denied** (401) |
| Device identifiers? | Stub `Device` model only — no client UUID, no JWT claim; store nullable `device_id` for future, no per-device progress rows |
| Redis needed? | **No** — PostgreSQL upsert is authoritative |

## Existing stubs

- `WatchHistory` table from migration 001 is unused by APIs: ambiguous `content_type`/`content_id`, no uniqueness, snapshot title/poster, no asset FK.
- Frontend Watch History / Continue Watching / Profile counts are **mock-only**.
- Continue Watching is hidden entirely in API mode today.
- Player keeps `currentTime`/`duration` in memory only (no persistence).

## Route identifiers

| Route | ID |
| --- | --- |
| `/player/movie/:id` | `Movie.id` (int) |
| `/player/episode/:id` | `Episode.id` (int) |
| `/player/asset/:assetId` | `MediaAsset.id` (UUID string) — admin/test; **no** customer history |

## Progress representation (decision)

Canonical key: `(subscriber_id, media_asset_id)` with exactly one of `movie_id` | `episode_id`.  
Server derives ownership from the asset; clients send asset id + position + optional session id + event timestamp.  
Duration: prefer active package `duration_seconds`, else asset probe duration; clamp client position.  
Completion: ≥ `WATCH_PROGRESS_COMPLETE_PERCENT` (default 90) or explicit complete / near-end.

## Unpublish / delete policy

- Preserve private history rows.
- Continue Watching: exclude unpublished/archived/deleted and unplayable (no active package).
- History list: may show `available=false` generic entry (no unpublished metadata leak).
- Playback resume denied until republished.

## Competing systems

Replace unused `watch_history` stub with normalized `user_watch_progress` (migration 009). Do not keep both write paths.

## Deferred

Payments, entitlements, recommendations, analytics platform, Cloudflare/CDN/R2/S3, DRM, subtitles, offline, TV apps, Phase 11.
