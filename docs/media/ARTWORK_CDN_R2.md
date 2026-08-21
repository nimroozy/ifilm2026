# Artwork & trailer CDN via Cloudflare R2

**Status:** Implemented behind flags (default **OFF**)  
**Goal:** Store public website images (posters, backdrops, logos, stills) and optional trailer binaries on **Cloudflare R2**, served through a Cloudflare CDN custom domain. **Full movies / HLS stay on the VPS** (`MEDIA_ROOT`).

No AWS S3 or MinIO is required for this path. R2 uses the S3 API; this app already speaks that protocol.

## What this is / is not

| In scope | Out of scope |
|----------|----------------|
| TMDB/demo artwork → R2 + public CDN URL | Full library / HLS movie packages on public R2 |
| Optional trailer **video files** under `MEDIA_ROOT/trailers` | YouTube embed trailers (already third-party CDN) |
| Admin R2 settings: `public_base_url`, `artwork_cdn_enabled` | Enabling branch-cache / client redirects |
| Local `ARTWORK_ROOT` + `/artwork` kept as fallback | Replacing A1 session-authorized playback |

## Operator setup

1. Create an R2 bucket (recommend a dedicated public bucket for artwork, not private movie packages).
2. Attach a **custom domain** in Cloudflare (e.g. `cdn.ifilm.af`) so the CDN caches images.
3. Create an R2 API token with Object Read/Write on that bucket.
4. On the host `/etc/ifilm/ifilm.env` (or staging env):

```bash
ENABLE_ARTWORK_CDN_SYNC=true
ARTWORK_CDN_PUBLIC_BASE_URL=https://cdn.ifilm.af
R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_BUCKET=ifilm-artwork
R2_REGION=auto
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
```

Or leave env R2 empty and configure the same values under **Admin → Cloudflare R2**, including:
- Public CDN base URL
- “Publish artwork to R2 CDN” toggle  

The env master switch `ENABLE_ARTWORK_CDN_SYNC` must still be `true` (production compose defaults it to `false`).

5. Restart API/workers so settings reload.
6. Re-import/replace TMDB artwork (or reseed demo) so new files publish to R2. Existing DB URLs that still point at `/artwork/...` continue to work from the VPS until rewritten.

## Object keys

`{MEDIA_OBJECT_KEY_PREFIX}/v1/{posters|backdrops|logos|stills|trailers}/...`

Public URL: `{ARTWORK_CDN_PUBLIC_BASE_URL}/{object_key}`

## Failure behavior

- Local file write always succeeds first.
- CDN publish failures are logged and **do not** break imports; URL stays `/artwork/...`.
- Never deletes local artwork on successful publish.

## Related flags (keep false for this use case)

- `ENABLE_OBJECT_STORAGE` / MinIO origin — not required
- `ENABLE_R2_HOT_TIER` — capped **movie** hot tier, separate concern
- `ENABLE_CDN_SYNC` — legacy stub; must stay false
- `ENABLE_ORIGIN_PACKAGE_SYNC` — HLS packages only; leave off until intentionally cut over
