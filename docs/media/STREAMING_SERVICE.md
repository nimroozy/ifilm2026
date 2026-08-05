# Protected HLS streaming service (Phase 7)

Local, session-protected delivery of **completed active** HLS packages produced by Phase 6 encoding.

## What this phase provides

- Opaque playback tokens (URL path) with hashed storage
- Short-lived playback sessions (create / revoke / expire → HTTP 410)
- In-memory master + variant playlist rewriting onto `/api/stream/{token}/…`
- Segment delivery with HTTP Range (206 / 416)
- Explicit **active package** selection (`media_packages.is_active`)
- Narrow `PlaybackEligibilityService` (admin always; subscriber = published catalog only)
- Admin playback-session list / revoke UI
- Docker: API mounts packages **read-only**; worker mounts packages **read-write**; originals RO for worker

## What this phase does **not** provide

- Cloudflare Stream / CDN / R2 / S3
- DRM / encryption
- Customer player integration
- Subscription / payment / Radius entitlement rules (deferred)
- Watch history / analytics products
- Public `/media` StaticFiles of `MEDIA_ROOT` (removed)

## Feature flags

| Variable | Default | Role |
| --- | --- | --- |
| `ENABLE_LOCAL_STREAMING` | `false` | Gates session APIs and stream delivery |
| `PLAYBACK_TOKEN_SECRET` | empty | Required (≥32 chars) when streaming enabled; HMAC key for token hashes |
| `PLAYBACK_TOKEN_TTL_SECONDS` | `3600` | Session lifetime |
| `ARTWORK_ROOT` | `./artwork` | Optional public artwork tree at `/artwork` (never packages/originals) |

Encoding still requires `ENABLE_MEDIA_PROCESSING` + `ENABLE_HLS_ENCODING`.

## Active package lifecycle

1. Encode completes → validate → atomic promote → write renditions → `status=completed`
2. Worker calls `activate_completed_package` in the **same transaction**
3. Prior active package for the asset is marked inactive + `superseded_at`
4. New package gets `is_active=true` + `activated_at`
5. Partial unique index: at most one active HLS package per asset
6. Playback session creation **requires** an active completed package (no silent fallback)

Failed / cancelled / in-flight packages cannot be active. Older completed packages remain on disk.

Migration `007_streaming_service` backfills: newest completed HLS package per asset becomes active.

## Token design

- 32 cryptographically random bytes → URL-safe base64 (no padding)
- Returned **once** at session creation
- DB stores HMAC-SHA256(`PLAYBACK_TOKEN_SECRET`, token) hex digest
- Transport: `/api/stream/{opaque_token}/master.m3u8` (HLS clients)
- No query-string tokens; no Authorization header transport in Phase 7
- Logs redact `/api/stream/{token}/` → `/api/stream/[REDACTED]/`
- Admin APIs never return raw token, token hash, or filesystem paths

## Eligibility

`PlaybackEligibilityService.can_play(principal, media_asset)`:

| Principal | Rule |
| --- | --- |
| Admin (active) | Allowed (operational verification) |
| Subscriber (active) | Allowed only if linked movie/episode/series/season is `published` and not soft-deleted |
| Unauthenticated / unknown owner | Denied |

Subscriber **entitlement** (plans, payment, Radius packages) is **deferred** — do not invent it here.

## Stream routes

| Method | Path | Auth |
| --- | --- | --- |
| GET | `/api/stream/{token}/master.m3u8` | Valid session token |
| GET | `/api/stream/{token}/{label}/index.m3u8` | Valid session token |
| GET | `/api/stream/{token}/{label}/{segment}.ts` | Valid session token (+ Range) |
| POST | `/api/admin/playback/sessions` | `streaming.manage` |
| GET | `/api/admin/playback/sessions` | `streaming.read` |
| POST | `/api/admin/playback/sessions/{id}/revoke` | `streaming.manage` |

## External media playback (limitation)

Validated external HTTPS MP4/HLS assets can create a playback session **without** an active
local package. Session creation still enforces:

- local streaming enabled
- principal eligibility (admin bypass / subscriber published + entitlement)
- external URL previously validated and attached

**Contract:** the player uses `playback_url` / `source_type` from `PlaybackSessionCreated`.
For `source_type=external`, `playback_url` is the validated CDN URL (also mirrored on
`master_playlist_url` for compatibility).

**Limitation (not parity with packaged HLS):** iFilm does **not** proxy or rewrite external
segments. After the session is authorized and the URL is returned, subsequent fetches go
directly to the external host. Session expiry/revocation does not revoke CDN access to that
URL. Do not claim tokenized `/api/stream/{token}/…` protection for external sources.

Packaged HLS remains the protected path: playlists and segments are rewritten through the
session token.

## Legacy removal

- Public `StaticFiles` mount of `MEDIA_ROOT` at `/media` **removed** (404 with explanation)
- Placeholder `write_placeholder_package` **removed**
- Legacy `GET /api/stream/{type}/{id}` and `GET /api/media/hls/...` **removed**
- One authoritative streaming implementation: `app/services/streaming/` + `app/api/routes/stream.py`

## Docker mounts

| Service | originals | packages | artwork |
| --- | --- | --- | --- |
| `api` | RW (uploads) | **RO** | RO `/data/artwork` |
| `media-processing-worker` | **RO** | **RW** (includes `packages/work`) | — |

Verify API package mount:

```bash
docker compose config | grep -A6 ifilm_media_packages
# api service should show read_only: true for packages
```

## Migration

```bash
alembic upgrade head   # 007_streaming_service
```

Round-trip: `006 → 007 → 006 → 007`.

## Admin UI

`/admin/media/playback-sessions` — list/filter/revoke. Does not display tokens or paths.
