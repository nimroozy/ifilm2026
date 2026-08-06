# Adaptive HLS video player (Phase 8)

Customer-facing adaptive playback using the **protected Phase 7 streaming service**.

## Architecture

| Piece | Role |
| --- | --- |
| `src/pages/PlayerPage.tsx` | Route resolver (movie / episode / asset) + auth gate |
| `src/player/VideoPlayer.tsx` | Composition root |
| `usePlaybackSession` | Session create / one-shot 410 refresh / revoke on unmount |
| `useHlsPlayer` | Native HLS **or** `hls.js` (never both) |
| `PlayerControls` | Play, seek, volume, fullscreen, PiP, speed |
| `QualitySelector` | Auto + manifest levels (hls.js only) |
| `AudioTrackSelector` | Manifest audio tracks when >1 (external HLS only today) |
| `SubtitleSelector` | Manifest text tracks + Off; local packaging deferred |
| `PlaybackError` / `PlayerLoadingState` | Safe UX (no tokens in messages) |

## Native HLS vs hls.js

1. **Apple Safari / iOS only:** if `canPlayType('application/vnd.apple.mpegurl')` is usable → **native** (`video.src = masterUrl`). Quality selector explains browser-managed ABR. Chromium often returns `"maybe"` for HLS without reliable native playback — we **do not** treat that as native.
2. Else if `Hls.isSupported()` → **hls.js** with conservative retries (bounded network/media recoveries).
3. Else → unsupported browser error.

Hls instances and listeners are destroyed on unmount, URL change, and fatal errors. Never attach native and hls.js at the same time.

**Verification status:** native selection/lifecycle is **unit-simulated**. Real Safari playback is **not verified** in CI/cloud agents.

## Playback-session lifecycle

1. Require subscriber JWT (`tokenStore`) or admin JWT (ops test / asset route).
2. `POST /api/playback/sessions` with `{content_type, content_id}` or `{media_asset_id}`.
3. Hold `master_playlist_url` / token **only in component memory**.
4. Load protected master; start when ready.
5. On unmount: destroy engine; best-effort revoke with the matching principal client.

### Session expiration / 410 refresh

- **hls.js:** fatal `NETWORK_ERROR` with HTTP 410 → classify response body:
  - `expired` / unknown → **one** automatic session refresh + restore `currentTime`
  - `revoked` → **no** refresh; safe error UI
- Bound: `MAX_AUTO_REFRESH = 1` per player mount.
- **Native HLS:** media `error` best-effort refresh (browsers do not expose HTTP 410). Not claimed as fully verified without Safari.

## Routes

| Path | Target |
| --- | --- |
| `/player/movie/:id` | Catalog movie → resolve playable asset |
| `/player/episode/:id` | Catalog episode |
| `/player/asset/:assetId` | Admin protected play test (same session APIs) |
| `/player/:id` | Legacy → movie (or `?ep=` episode) |

## CSP (enforced)

Authoritative layer: FastAPI `SecurityHeadersMiddleware` (`app/core/csp.py` + `app/core/security_headers.py`).

When `FRONTEND_DIST` points at `app/frontend/dist`, the API also serves the SPA so HTML documents receive the same CSP.

**Production policy (exact directives):**

```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
img-src 'self' data: blob: https:;
font-src 'self' data: https://fonts.gstatic.com;
connect-src 'self' blob:;
media-src 'self' blob:;
worker-src 'self' blob:;
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
form-action 'self';
```

`CSP_MODE=production|development` overrides derivation from `APP_ENV`. Development adds `unsafe-eval` + Vite HMR websocket/connect origins only.

Vite `server` / `preview` headers mirror the same policies for split hosting, but prefer `FRONTEND_DIST` so one middleware owns the header.

## Security and token handling

- No token in storage / analytics / UI errors
- Error text redacts `/api/stream/{token}`
- Network panel will show requested URLs (expected); the app must not persist, render, or log them
- No `dangerouslySetInnerHTML` for stream content
- Player route accepts only catalog/asset ids

## Keyboard / mobile / a11y

Space/K · ←/→ · ↑/↓ · M · F. Ignored in inputs. `playsInline`, safe-area, touch controls, auto-hide chrome, RTL via `dir`.

## Local verification

```bash
# Prepare encoded 640×360 asset (writes /tmp; does not commit media)
python3 scripts/prepare_phase8_verify_asset.py

# Serve production SPA + API with CSP
# FRONTEND_DIST=.../app/frontend/dist CSP_MODE=production uvicorn ...

cd app/frontend
pnpm exec playwright test -c playwright.phase8.config.ts
```

## Deferred

Watch history / Continue Watching are implemented for authenticated subscribers (see [docs/user/WATCH_HISTORY.md](../user/WATCH_HISTORY.md)). Still deferred: payments/entitlement, DRM, **multi-track local packaging** (`EXT-X-MEDIA` audio groups + subtitle playlists), CDN/Cloudflare/R2/S3, casting, TV apps, analytics platform, offline downloads.

Catalog `audio_availability` / `subtitle_availability` expose truthful metadata with `selectable_in_player: false` until local multi-track packaging ships (see [AUDIO_SUBTITLE_AVAILABILITY.md](../catalog/AUDIO_SUBTITLE_AVAILABILITY.md)).
