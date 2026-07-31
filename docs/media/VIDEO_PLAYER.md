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
| `AudioTrackSelector` | Manifest audio tracks when >1 |
| `SubtitleSelector` | Placeholder (pipeline deferred) |
| `PlaybackError` / `PlayerLoadingState` | Safe UX (no tokens in messages) |

## Native HLS vs hls.js

1. If `video.canPlayType('application/vnd.apple.mpegurl')` is usable → **native** (`video.src = masterUrl`). Quality selector explains browser-managed ABR.
2. Else if `Hls.isSupported()` → **hls.js** with conservative retries (bounded network/media recoveries).
3. Else → unsupported browser error.

Hls instances and listeners are destroyed on unmount, URL change, and fatal errors. Never attach native and hls.js at the same time.

## Playback-session lifecycle

1. Require subscriber JWT (`tokenStore`) or admin JWT (ops test / asset route).
2. `POST /api/playback/sessions` with `{content_type, content_id}` or `{media_asset_id}`.
3. Hold `master_playlist_url` / token **only in component memory** (never localStorage / sessionStorage / IndexedDB / cookies / analytics / Redux).
4. Load protected master; start when ready.
5. On unmount: destroy engine; best-effort revoke with the matching principal client.

### Session expiration / 410 refresh

- **hls.js:** fatal `NETWORK_ERROR` with HTTP 410 triggers one refresh.
- **Native HLS:** media `error` event triggers one best-effort refresh (browsers do not expose the HTTP status).
- Bound: at most **one** automatic session refresh per player mount (`MAX_AUTO_REFRESH = 1`).
- Prior `currentTime` is restored after metadata loads (clamped to duration).
- Further failures show a safe non-retryable error without the raw playback URL.

## Routes

| Path | Target |
| --- | --- |
| `/player/movie/:id` | Catalog movie → resolve playable asset |
| `/player/episode/:id` | Catalog episode |
| `/player/asset/:assetId` | Admin protected play test (same session APIs) |
| `/player/:id` | Legacy → movie (or `?ep=` episode) |

Browse / Index / Account Watch links use `/player/movie/:id` or `/player/episode/:id`. Backend selects the **active** completed package. Clients never pick packages or supply stream URLs.

## Quality selection

Levels come **only** from the loaded HLS manifest (`MANIFEST_PARSED`). Labels map height → 240p / 360p / 480p / 720p / 1080p. Auto restores ABR (`currentLevel = -1`). Native HLS hides manual selection with an explanation.

## Error recovery

Handled safely (no token leakage): auth required, streaming disabled, no active package, session create failure, network/media errors, unsupported browser, expired/revoked (410), fatal hls.js errors. Recoverable network/media errors retry a bounded number of times then stop.

## Keyboard

Space/K play-pause · ←/→ seek · ↑/↓ volume · M mute · F fullscreen. Ignored while typing in inputs/selects/contenteditable. Esc exits fullscreen via the browser where applicable.

## Mobile

`playsInline`, touch-friendly controls, safe-area padding, auto-hide chrome on playback, controls reappear on tap/pointer move, volume control visible on small screens, no sound autoplay without gesture.

## Accessibility

ARIA labels on controls, `role="alert"` on errors, visible focus via existing button styles, keyboard usable without a mouse, screen-reader-friendly status copy. Subtitle control remains a deferred placeholder.

## Security and token handling

- No token in storage, analytics, UI errors, or intentional console logs of stream URLs
- Error text redacts `/api/stream/{token}`
- No `dangerouslySetInnerHTML` for stream content
- Player route accepts only catalog/asset ids — not arbitrary stream URLs
- Backend access logs redact stream token paths

## CSP requirements

There is no global CSP in the SPA host yet. When enabling CSP at the edge or static host, add **only** the minimum player-related directives:

```
media-src 'self' blob:;
connect-src 'self' blob:;
worker-src 'self' blob:;
```

Keep `script-src` / `default-src` as already required by the app shell. Do not broaden to arbitrary remote media origins. Same-origin `/api` (Vite proxy or reverse proxy) keeps stream fetches under `'self'`.

## Testing

- Unit: session hook, safe errors, hls vs native selection, destroy, quality list, keyboard, a11y labels, token redaction
- Backend: customer session by movie/episode, auth required, XOR validation, owner revoke, 409 no package, admin dual principal
- Real browser: use an encoded asset with `ENABLE_LOCAL_STREAMING=true` (Chrome required; Safari/native covered by unit simulation when Safari is unavailable)

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Sign in to watch | Subscriber or admin JWT present |
| Not ready for playback | Active completed HLS package on asset |
| Streaming unavailable | `ENABLE_LOCAL_STREAMING=true` + `PLAYBACK_TOKEN_SECRET` |
| Quality list empty on Chrome | Manifest parsed? hls.js path? |
| Quality unavailable on iPhone | Expected — native ABR |
| Infinite loading after expiry | Refresh already used once — retry manually |

## Deferred

Watch history / Continue Watching, payments/entitlement, DRM, subtitle packaging, CDN/Cloudflare/R2/S3, casting, TV apps, analytics, offline downloads.
