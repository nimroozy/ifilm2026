# Subscriber Authentication

Phase 11 identity and session model for customer subscribers.

## Identity model

| Field | Meaning |
| --- | --- |
| Local `subscribers.id` | Stable internal subject used in JWT `sub` |
| `identity_provider` | `fixture` \| `radius` \| `local` |
| `external_subject` | Provider correlation id (fixture username / Radius User-Name) |

Radius / fixture passwords are **never** stored. Local Argon2 hashes are reserved for admin (and any future local-only accounts).

## Token types

| Token | `typ` claim | Notes |
| --- | --- | --- |
| Subscriber access JWT | `subscriber` | Short-lived; cannot call admin APIs |
| Subscriber refresh | opaque (hashed at rest) | Rotating; reuse revokes family |
| Admin access JWT | `admin` | Separate issuer path |

## Endpoints

- `POST /api/auth/subscriber/login` (alias: `POST /api/auth/login`)
- `POST /api/auth/subscriber/refresh`
- `POST /api/auth/subscriber/logout` (alias: `POST /api/auth/logout`)
- `GET /api/me`
- `GET /api/me/entitlement`
- `GET /api/me/devices`
- `DELETE /api/me/devices/{id}`

## Radius adapter (`SubscriberIdentityProvider`)

Modes via `SUBSCRIBER_IDENTITY_MODE`:

| Mode | When |
| --- | --- |
| `fixture` | Development/test only (`RADIUS_MOCK_USERS`) |
| `radius` | Live SAS/FreeRADIUS (fail-closed) |
| `disabled` | All subscriber auth denied |

Compatibility: if mode is `disabled` but `ENABLE_RADIUS_LOGIN=true`, `RADIUS_MODE=mock|live` maps to fixture/radius.

### Live Radius assumptions (unverified)

- Access-Accept proves identity only
- SAS attribute → package/branch/expiry mapping is **not verified**
- Account-status / entitlement queries against live SAS are **not implemented**
- Do not claim live SAS verification unless staging-tested

Required Radius request attributes today: `User-Name`, `User-Password`, `NAS-Identifier`.

## Security

- Generic invalid-credential errors (no username enumeration)
- No password / Radius secret / raw provider response logging
- Login rate limiting (`SUBSCRIBER_LOGIN_RATE_LIMIT`)
- Fixture mode rejected outside development/test
- Refresh-token rotation + reuse detection
- Logout revokes refresh family
- Subscriber/admin token isolation

## Device limits

- Client stores an app-generated `device_id` (`ifilm_device_id`)
- Server enforces `max_devices`
- Revoke cascades to refresh tokens and linked playback sessions

## Test vs live

| Environment | Recommended mode |
| --- | --- |
| Local / CI | `fixture` + `RADIUS_MOCK_USERS` |
| Staging/production | `radius` only after SAS attribute mapping is verified; otherwise keep login disabled |

## Deployment configuration

See `app/backend/.env.example`:

- `SUBSCRIBER_IDENTITY_MODE`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `SUBSCRIBER_MAX_DEVICES_DEFAULT`
- `ENTITLEMENT_CACHE_TTL_SECONDS`
- `ENTITLEMENT_CACHE_GRACE_SECONDS` (default `0` — expired cache never authorizes)
- `RADIUS_*`

## Troubleshooting

| Symptom | Check |
| --- | --- |
| 503 on login | Provider unavailable / mode disabled / Radius timeout |
| 403 `device_limit_exceeded` | Revoke a device via `/api/me/devices` |
| 403 `account_disabled` | Fixture/provider account status |
| Refresh 401 `refresh_reuse` | Token replay — family revoked; re-login |
