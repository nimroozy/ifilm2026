# Hybrid CDN Phase 2 — origin sync & read fallback

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-foundation-4873` (PR #81)  
**Branch:** `cursor/hybrid-cdn-phase2-origin-delivery-4873`

## Boundary

**In scope**
- Idempotent post-activate sync of HLS package trees to central origin (`ObjectStorage`)
- Durable sync state on `media_packages` (migration `026_origin_package_sync_v1`)
- Worker job type `origin_sync` with retry; never un-activates local package
- Optional token-gated origin read fallback for master/variant/segment when local file missing
- Playlist rewrite still emits `/api/stream/{token}/…` only

**Deferred**
- Syncing originals/artwork as required path
- R2 hot-tier promote/demote automation
- Branch caches / Cloudflare Stream
- Making publish readiness require origin sync
- Presigned public URLs
- Destructive origin lifecycle

## Failure / fallback semantics

| Event | Behavior |
|-------|----------|
| Flags OFF | Encode/promote/stream unchanged (local-only) |
| Sync enqueue failure after encode | Logged; local package stays active |
| Transient sync failure | Job `retry_wait`; `origin_sync_status=pending/failed`; package `is_active` unchanged |
| Permanent sync failure | Job failed; `origin_sync_status=failed`; local playback OK |
| Read fallback OFF / not synced | Local miss → 404/400 as today |
| Read fallback ON + synced | Local miss → fetch origin bytes → same rewrite/Range/content-type |

## Security

- Session authorization unchanged before any origin read
- Object keys confined to `origin_object_prefix` / package id
- No permanent S3/R2 URLs, buckets, or credentials in responses
- Provider errors mapped to generic `StreamPathError` (no secret leakage)
- Legacy `ENABLE_CDN_SYNC` remains rejected in staging/production

## Rollback

1. Keep flags false (or set false) — no origin I/O
2. Optional: Alembic downgrade `026` → `025` only in non-production after confirming no dependency on new columns
3. Local packages and playback sessions unchanged
