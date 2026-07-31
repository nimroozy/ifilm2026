# Media Upload Foundation

## Architecture summary

This phase adds a **local filesystem upload pipeline** for administrators:

1. Create an **upload session** + **media asset** row (`POST /admin/media/sessions`)
2. Stream file bytes into `MEDIA_ROOT/temp/` (`PUT /admin/media/sessions/{id}`)
3. Finalize into `MEDIA_ROOT/<category>/<asset_id>/…`, store SHA256, mark completed
4. Inspect metadata (`GET /admin/media/assets/{id}`) or cancel before completion

Encoding, HLS, CDN, S3/R2, signed URLs, thumbnails, and playback are **out of scope**.

Feature flag: `ENABLE_UPLOADS` (default `false`).

Permissions:

| Required | Satisfied by |
| --- | --- |
| `upload.read` | `upload.read`, `upload.manage`, `upload` |
| `upload.manage` | `upload.manage`, `upload` |

## Database schema

### `media_assets`

- UUID primary key
- Optional single owner: `movie_id` | `series_id` | `season_id` | `episode_id` (CHECK ≤ 1)
- `original_filename`, `stored_filename`, `mime_type`, `extension`
- `size_bytes`, `checksum_sha256`
- `width`, `height`, `duration_seconds` (nullable; filled by future processors)
- `storage_backend` (`local`), `storage_path`, `category`
- `upload_status`, `processing_status` (`none` in this phase)
- timestamps + `created_by_admin_id`

### `upload_sessions`

- UUID primary key, FK → `media_assets`
- `expected_size_bytes`, `bytes_received`, `status`, `temp_path`, `error`, `expires_at`

Alembic revision: `004_media_upload` (revises `003_catalog_admin`).

## Storage layout

Configured via `MEDIA_ROOT`:

```
media/
  originals/
  posters/
  backdrops/
  trailers/
  subtitles/
  temp/
```

Final object path: `<category>/<asset_uuid>/<stored_filename>`.

## API list

| Method | Path | Permission |
| --- | --- | --- |
| POST | `/api/admin/media/sessions` | `upload.manage` |
| PUT | `/api/admin/media/sessions/{session_id}` | `upload.manage` |
| GET | `/api/admin/media/sessions/{session_id}` | `upload.read` |
| DELETE | `/api/admin/media/sessions/{session_id}` | `upload.manage` |
| GET | `/api/admin/media/assets` | `upload.read` |
| GET | `/api/admin/media/assets/{asset_id}` | `upload.read` |

Validation rejects: unsupported MIME, oversized files, zero-byte files, path traversal, executables, and (when `UPLOAD_REJECT_DUPLICATE_CHECKSUM=true`) duplicate completed checksums.

## Admin UI

Minimal pages (existing design system):

- `/admin/tools/upload` — upload form + recent assets
- `/admin/media/:assetId` — media asset metadata

Screenshots:

![Admin media upload](screenshots/admin-media-upload.png)

![Admin media asset detail](screenshots/admin-media-asset-detail.png)

## Deferred

FFmpeg, HLS/DASH, subtitle processing, artwork resizing, CDN sync, object storage, playback, DRM, signed URLs.
