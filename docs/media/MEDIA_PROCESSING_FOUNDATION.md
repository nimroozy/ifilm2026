# Media Processing Foundation

## Architecture summary

This phase adds **ffprobe-based media probing** for completed uploads:

1. Admin queues a **probe** job for a completed `media_asset`
2. A dedicated worker (`python -m app.workers.media_processing`) claims jobs atomically
3. The worker validates the asset path under `MEDIA_ROOT`, runs **ffprobe** (JSON), parses metadata, and persists it
4. Progress and diagnostics are visible via API and admin UI

Encoding profiles, HLS/DASH packaging, CDN, playback, DRM, thumbnails, and subtitle conversion are **out of scope**.

Feature flag: `ENABLE_MEDIA_PROCESSING` (default `false`). HLS packaging additionally requires `ENABLE_HLS_ENCODING` (see `docs/media/HLS_ENCODING_PIPELINE.md`).

Permissions:

| Required | Satisfied by |
| --- | --- |
| `processing.read` | `processing.read`, `processing.manage`, `processing` |
| `processing.manage` | `processing.manage`, `processing` |

## Lifecycle

```
queued → running → completed
                 ↘ failed
                 ↘ cancelled
queued/running → retry_wait → (eligible) → running
```

Discrete probe progress: `0 queued → 10 claimed → 30 validating → 50 ffprobe → 75 parsing → 90 saving → 100 completed`.

## Worker model

- Separate process: `python -m app.workers.media_processing`
- Does **not** run inside HTTP requests
- Polls every `MEDIA_PROCESSING_POLL_SECONDS`
- Claims with PostgreSQL `FOR UPDATE SKIP LOCKED` (SQLite falls back to `WITH FOR UPDATE`)
- Heartbeats while running; stale jobs (no heartbeat beyond `MEDIA_PROCESSING_STALE_AFTER_SECONDS`) move to `retry_wait` or `failed`
- Multiple workers cannot claim the same job

## Retry policy

| Kind | Examples | Behavior |
| --- | --- | --- |
| Permanent | missing file, path escape, corrupt/unsupported media, bad JSON | fail (or cancel) |
| Transient | timeout, temporary I/O / worker death | `retry_wait` with exponential backoff (`MEDIA_PROCESSING_RETRY_BASE_SECONDS * 2^(attempt-1)`) until `max_attempts` |

## Cancellation

- `queued` / `retry_wait`: immediate `cancelled`
- `running`: sets `cancel_requested`; worker terminates the process group (SIGTERM then SIGKILL)
- Never deletes the original uploaded media
- Idempotent on terminal jobs

## ffprobe command

Argument array only (`shell=False`):

```
ffprobe -v error -print_format json -show_format -show_streams <resolved-path>
```

Path security:

- upload must be `completed`
- storage backend must be `local`
- resolved path must stay inside `MEDIA_ROOT`
- must be a regular file; symlink escapes rejected
- bounded stdout/stderr capture (`MEDIA_PROCESSING_LOG_MAX_BYTES`)

## Metadata selection rules

- **Video**: first video stream with `disposition.default=1`, else first video stream by index
- **Audio**: same among audio streams
- **Subtitle count**: streams with `codec_type` in `{subtitle, text}`
- Missing / `N/A` / invalid numerics → `null`
- Rational rates like `24000/1001` evaluated when denominator ≠ 0
- Filtered `probe_json` stores a bounded subset (no secrets / env)

## Database

Alembic revision: `005_media_processing` (revises `004_media_upload`).

- `media_processing_jobs` + partial unique index `uq_media_processing_active_probe` on `(media_asset_id, job_type)` where status ∈ `{queued,running,retry_wait}` and `job_type='probe'`
- `media_processing_job_events` for queued/claimed/started/retry/failed/cancelled/completed/stale_recovered
- Probe columns on `media_assets` (container, codecs, rates, stream counts, filtered JSON, `probed_at`)

## API

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/api/admin/media/processing/status` | `processing.read` |
| POST | `/api/admin/media/assets/{id}/processing/probe` | `processing.manage` |
| GET | `/api/admin/media/assets/{id}/processing` | `processing.read` |
| GET | `/api/admin/media/processing/jobs` | `processing.read` |
| GET | `/api/admin/media/processing/jobs/{id}` | `processing.read` |
| POST | `/api/admin/media/processing/jobs/{id}/retry` | `processing.manage` |
| DELETE | `/api/admin/media/processing/jobs/{id}` | `processing.manage` |

## Configuration

See `app/backend/.env.example` for `ENABLE_MEDIA_PROCESSING`, `FFMPEG_BINARY`, `FFPROBE_BINARY`, poll/heartbeat/stale/retry/timeout/log limits.

The web API does **not** crash if processing is disabled or binaries are missing. The worker exits non-zero if enabled but binaries are unavailable.

## Docker

- Backend image installs `ffmpeg`
- Compose service `media-processing-worker` runs `python -m app.workers.media_processing`
- Media volume is mounted **read-write** so the same worker can write HLS packages when encoding is enabled (intentional; see HLS docs)
- Legacy ARQ `worker` service remains for other placeholders

## systemd

Example unit: `app/backend/systemd/ifilm-media-processing.service`

## Admin UI

- Asset detail: probe metadata + Probe / Retry / Cancel with polling that stops on terminal states
- `/admin/media/processing`: job list with status/type/asset filters

## Troubleshooting

| Symptom | Check |
| --- | --- |
| 503 on processing APIs | `ENABLE_MEDIA_PROCESSING` |
| Worker exits immediately | flag off, or ffmpeg/ffprobe missing |
| Jobs stuck running | stale recovery / heartbeat settings |
| Path security errors | file under `MEDIA_ROOT`, completed upload |

## Deferred

HLS/DASH, encode profiles, GPU, CDN/S3/R2, playback URLs, DRM, thumbnails, subtitle conversion, automatic publishing, distributed queue brokers beyond this DB worker.
