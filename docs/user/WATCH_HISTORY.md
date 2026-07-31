# Watch History & Continue Watching

**Phase:** 10  
**Migration:** `009_watch_history` (revises `008_publishing_workflow`)

## Identity

Only authenticated **subscribers** (`JWT typ=subscriber`) own watch progress.

| Principal | History |
| --- | --- |
| Subscriber | Full `/api/me/*` access to own rows |
| Admin | Forbidden (403) — operational playback does not create history |
| Anonymous | Denied (401) |

## Data model

Table `user_watch_progress` — one row per `(subscriber_id, media_asset_id)` with exactly one of `movie_id` | `episode_id`.

Key fields: `position_seconds`, `duration_seconds`, `progress_percent`, `completed`, `last_event_at`, optional `playback_session_id` / `device_id`.

The unused stub `watch_history` table is dropped by migration 009.

## Progress lifecycle

1. Subscriber plays a published movie/episode with an active HLS package.
2. Client upserts progress with `event_at` (UTC).
3. Server clamps position, derives duration from package/asset, computes percent.
4. Completion when percent ≥ `WATCH_PROGRESS_COMPLETE_PERCENT` (default **90**) or explicit complete.
5. Stale events (`event_at` &lt; `last_event_at`) are ignored.
6. Completion is not rolled back by stale or lower-position updates.
7. **Start Over** (`start_over=true`) resets position and completed.

### Thresholds (defaults)

| Setting | Default |
| --- | --- |
| `WATCH_PROGRESS_MIN_SECONDS` | 30 |
| `WATCH_PROGRESS_COMPLETE_PERCENT` | 90 |
| `WATCH_PROGRESS_SAVE_INTERVAL_SECONDS` | 20 |
| `WATCH_PROGRESS_RESUME_MARGIN_SECONDS` | 10 |
| `CONTINUE_WATCHING_LIMIT` | 20 |

## Client save cadence

- Every ~20s while playing
- On pause / significant seek
- On `visibilitychange` hidden / `pagehide` / cleanup
- On ended / complete
- Failures must not stop playback
- Never send playback tokens in progress requests or logs

## Continue Watching

Incomplete rows with `position_seconds ≥ MIN`, currently published, and playable (active HLS package). Sorted by `last_watched_at` desc. No package IDs, tokens, or filesystem paths.

## Watch History

Paginated list of all rows for the user. Unavailable (unpublished/archived/unplayable) items return `available=false` with generic title and empty poster/player path — private row retained until user deletes.

## Multi-device

One canonical row per user/content. Last-write-wins via `last_event_at`. Device id is optional diagnostics only.

## Playback session relation

Optional `playback_session_id` validated: same subscriber, same asset. Raw tokens never accepted. Unload after token expiry may omit session id.

## Unpublish integration

Hide from Continue Watching; deny playback; preserve history; show unavailable tombstone.

## API

```
PUT    /api/me/watch-progress/{asset_id}
GET    /api/me/watch-progress/{asset_id}
POST   /api/me/watch-progress/{asset_id}/complete
GET    /api/me/continue-watching
GET    /api/me/watch-history
DELETE /api/me/watch-history/{asset_id}
DELETE /api/me/watch-history
```

## Privacy

No public history endpoints. No admin browse in this phase. Behavioral data purpose-limited to resume/history. Clear All / remove item supported. Retention: until user deletion (document longer backup retention separately if backups exist).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Progress not saving | Subscriber token? `ENABLE_WATCH_HISTORY`? Asset linked to movie/episode? |
| Not in Continue Watching | Position ≥ 30s? Not completed? Content published + active package? |
| Resume seeks wrong | Server duration vs player duration; resume margin |
| 403 on /api/me | Using admin token instead of subscriber |

## Deferred

Payments, entitlements, recommendations, analytics platform, Cloudflare/CDN/R2/S3, DRM, subtitles, offline, TV apps, Phase 11.
