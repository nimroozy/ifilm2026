# Direct URL media import (server-to-server)

**Status:** Draft implementation (MP4 complete; HLS mirroring deferred)  
**Admin path:** Movie/Episode → Media → **Add Media** → Import from URL

## Modes

| Mode | Behavior |
|------|----------|
| Upload File | Existing browser upload (unchanged) |
| Import from URL | Browser submits URL only; worker streams HTTPS MP4 into protected `MEDIA_ROOT` |
| External Source | Existing Option A — remote-hosted URL; unprotected direct; ack required |

## Enablement

```bash
ENABLE_UPLOADS=true
ENABLE_REMOTE_MEDIA_IMPORT=true   # optional; ENABLE_UPLOADS alone also gates API
INTEGRATION_SECRETS_KEY=...       # encrypts source URLs at rest
ENABLE_MEDIA_PROCESSING=true      # worker must run to execute imports
```

## Deployment note

`media-processing-worker` mounts `originals` **read-write** so `remote_media_import`
can finalize `.part` files from `temp/` into protected `originals/` (EXDEV-safe).
Public artwork / R2 paths are never used for full movies.

## Safety

- Reuses `media_external.assert_safe_external_url` / validate (HTTPS, SSRF, no redirects)
- Revalidates DNS before connect (rebinding defense)
- Signed query tokens never returned/logged; ciphertext via Fernet
- Full movies never go to public artwork R2
- Public playability still requires packaged HLS readiness
- Accept-Ranges resume: partial `.part` kept on retryable failure; 206 + Content-Range required; ignored Range (200) restarts cleanly

## HLS

Complete HLS tree mirroring is **deferred**. Import from URL rejects `.m3u8` with a clear error.

## Protected remote proxy (future)

Documented only — not enabled: subscriber → entitlement → `/api/stream` proxy → remote origin.
