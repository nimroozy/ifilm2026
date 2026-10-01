# Direct URL media import (server-to-server)

**Status:** Draft implementation (MP4 complete; HLS mirroring deferred)  
**Admin path:** Movie/Episode → Media → **Add Media** → Import from URL

## Modes

| Mode | Behavior |
|------|----------|
| Upload File | Existing browser upload (unchanged) |
| Import from URL | Browser submits URL only; **remote-media-import-worker** streams HTTPS MP4 into protected `MEDIA_ROOT` |
| External Source | Existing Option A — remote-hosted URL; unprotected direct; ack required |

## Enablement

Both flags are required (neither alone is sufficient):

```bash
ENABLE_UPLOADS=true
ENABLE_REMOTE_MEDIA_IMPORT=true
INTEGRATION_SECRETS_KEY=...       # encrypts source URLs at rest
```

Remote import creates managed `MediaAsset` rows under the upload pipeline, so
`ENABLE_UPLOADS` remains a hard gate. Validate / start / retry / worker
execution all enforce both flags. GET status and cancel remain available for
already-created jobs after a flag flip.

## Workers / least privilege

| Worker | Claims | Mounts |
|--------|--------|--------|
| `media-processing-worker` | `probe`, `encode_hls`, `origin_sync` | source categories **RO**; packages/temp RW |
| `remote-media-import-worker` | `remote_media_import` only | **only** `temp` + `originals` RW |

`claim_next_job(..., allowed_job_types=...)` filters by `job_type` so workers
cannot steal each other's jobs. Public artwork / R2 paths are never used for
full movies.

Entrypoint:

```bash
python -m app.workers.remote_media_import
python -m app.workers.remote_media_import --healthcheck
```

ffmpeg/ffprobe are **not** required for import. After import completes
(`upload_status=completed`), use the normal probe → HLS package → publish flow.
Do not mark public playability from the import path.

## Safety

- Reuses `media_external.assert_safe_external_url` / validate (HTTPS, SSRF, no redirects)
- Revalidates URL safety immediately before GET (useful; **not** perfect DNS-rebinding
  prevention — httpx may resolve independently afterward; pinned-IP transport is a
  follow-up hardening item)
- Signed query tokens never returned/logged; ciphertext via Fernet
- Full movies never go to public artwork R2
- Public playability still requires packaged HLS readiness
- Accept-Ranges resume: partial `.part` kept on retryable failure; 206 + Content-Range
  required; ignored Range (200) restarts cleanly

## Alembic

This milestone adds `030_remote_media_import_v1` (single head from `029`).

Draft PR #93 currently also drafts a `030_*` revision and **must rebase after
this merges**, renumbering to `031_cdn_operations_v1` with
`down_revision = "030_remote_media_import_v1"`. Do not create two Alembic heads.

## HLS

Complete HLS tree mirroring is **deferred**. Import from URL rejects `.m3u8`
with a clear error.

## Protected remote proxy (future)

Documented only — not enabled: subscriber → entitlement → `/api/stream` proxy →
remote origin.
