# HLS Encoding Pipeline

## Architecture summary

Phase 6 extends the **existing media processing worker** with local **HLS VOD encoding**:

1. Admin queues an **`encode_hls`** job for a completed, **successfully probed** `media_asset`
2. The same worker (`python -m app.workers.media_processing`) claims jobs with PostgreSQL `SKIP LOCKED`
3. FFmpeg encodes H.264 + AAC renditions into a temporary workspace under `MEDIA_ROOT/packages/work/`
4. Output is validated (master + variant playlists, segments, no upscale)
5. The package is **atomically promoted** to `MEDIA_ROOT/packages/<asset_id>/<package_id>/`
6. Package/rendition rows are marked `completed` only after promotion

Feature flags (both default `false`):

| Flag | Controls |
| --- | --- |
| `ENABLE_MEDIA_PROCESSING` | Probe jobs, processing APIs, worker process |
| `ENABLE_HLS_ENCODING` | HLS encode queue/APIs (also requires media processing) |

HLS encode requires **both** flags. Probe requires only `ENABLE_MEDIA_PROCESSING`.

Permissions: same as probe — `processing.read` / `processing.manage`.

## Explicitly deferred

Cloudflare, CDN, R2, S3, remote storage, replication, playback API, public playlist delivery, signed URLs, DRM, video player, subtitle packaging, GPU encoding, watch history, recommendations, analytics.

## Lifecycle

```
queued → running → completed
                 ↘ failed
                 ↘ cancelled
queued/running → retry_wait → (eligible) → running
```

Package statuses: `pending → encoding → validating → promoting → completed` (or `failed` / `cancelled`).

Partial package paths are **not** exposed as completed in admin APIs until validation + promotion succeed.

## Encoding ladder

Seeded profiles (`media_encoding_profiles`): **240p, 360p, 480p, 720p, 1080p**.

- Cap: `HLS_MAX_HEIGHT` (default 1080)
- **Never upscale**: only profiles with `height <= min(source_height, HLS_MAX_HEIGHT)` are selected
- Video: H.264 (`libx264`), Audio: AAC
- HLS VOD segments: `HLS_SEGMENT_DURATION_SECONDS` (default **6**)
- Aligned keyframes: GOP ≈ `fps * segment_duration`, `-sc_threshold 0`, `-force_key_frames expr:gte(t,n_forced*N)`, `-hls_flags independent_segments`
- Progress: FFmpeg `-progress pipe:1` (structured key=value)

## Worker model

- Same process as probe: `python -m app.workers.media_processing`
- Dispatches by `job_type` (`probe` | `encode_hls`)
- Heartbeat, stale recovery, retry/backoff, cancellation (process group SIGTERM → SIGKILL)
- Temporary workspace cleaned on cancel/failure
- Original uploaded file is **never modified** (checksum verified after encode)

## Database

Alembic revision: **`006_hls_encoding`** (revises `005_media_processing`).

| Table | Purpose |
| --- | --- |
| `media_encoding_profiles` | Seeded ABR ladder |
| `media_packages` | Package lifecycle + storage paths |
| `media_renditions` | Per-variant metadata |

Partial unique index `uq_media_processing_active_encode_hls` ensures at most one active `encode_hls` job per asset (`queued` / `running` / `retry_wait`).

## API

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/api/admin/media/encoding/profiles` | `processing.read` |
| POST | `/api/admin/media/assets/{id}/processing/encode-hls` | `processing.manage` |
| GET | `/api/admin/media/assets/{id}/packages` | `processing.read` |
| GET | `/api/admin/media/packages/{id}` | `processing.read` |
| … | existing probe/job endpoints | unchanged |

## Configuration

See `app/backend/.env.example`:

- `ENABLE_MEDIA_PROCESSING` / `ENABLE_HLS_ENCODING`
- `MEDIA_PROCESSING_ENCODE_TIMEOUT_SECONDS`
- `HLS_SEGMENT_DURATION_SECONDS`
- `HLS_MAX_HEIGHT`
- `HLS_X264_PRESET`

When HLS encoding is disabled, the API starts normally even if FFmpeg is missing.
The worker requires **ffprobe** whenever media processing is enabled, and **ffmpeg** only when HLS encoding is also enabled.

## Docker

- `media-processing-worker` mounts `ifilm_media` **read-write** by design: the same worker probes originals and writes HLS package trees under `MEDIA_ROOT/packages/` (plus temporary workspaces). This is an intentional deployment change from the probe-only read-only mount.
- Healthcheck requires ffprobe always; ffmpeg only when `ENABLE_HLS_ENCODING=true`

## Admin UI

- Asset detail: **Encode HLS** (requires probe + dimensions), packages panel (paths only when `completed`)
- Processing jobs list: filter `probe` / `encode_hls`

## Troubleshooting

| Symptom | Check |
| --- | --- |
| 503 encode | `ENABLE_HLS_ENCODING` or `ENABLE_MEDIA_PROCESSING` |
| 409 encode | missing probe / no fitting profiles / active encode job |
| empty ladder | source height below 240p |
| packages stuck encoding | worker running, stale recovery, disk space under `MEDIA_ROOT` |
