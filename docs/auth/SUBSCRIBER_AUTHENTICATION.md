# Subscriber Authentication

Phase 11 identity and session model for customer subscribers.

> **PRODUCTION SAFETY — READ FIRST**
>
> 1. **Live SAS Radius authentication is unverified.**
> 2. **Radius attribute → entitlement mapping requires staging validation.**
> 3. **Production rollout of live Radius is blocked until staging verification is complete.**
> 4. Default `SUBSCRIBER_IDENTITY_MODE=disabled`. Do **not** enable live Radius in production.
> 5. `RADIUS_ENTITLEMENT_MAPPING_ENABLED` defaults to **false**. Access-Accept alone **never** grants playback.
> 6. Fixture mode is forbidden outside development/test.

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
| Subscriber refresh | opaque (hashed at rest) | Rotating; reuse detects family revoke |
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

Modes via `SUBSCRIBER_IDENTITY_MODE` (default **`disabled`**):

| Mode | When |
| --- | --- |
| `fixture` | Development/test only (`RADIUS_MOCK_USERS`) |
| `radius` | Live SAS/FreeRADIUS (fail-closed; live SAS unverified) |
| `disabled` | All subscriber auth denied (**production default**) |

Compatibility: if mode is `disabled` but `ENABLE_RADIUS_LOGIN=true`, `RADIUS_MODE=mock|live` maps to fixture/radius.

### Access-Accept vs entitlement (critical)

| Step | Behavior |
| --- | --- |
| Access-Accept | May establish **identity only** |
| Entitlement | Requires separately validated mapping + attributes |
| Mapping disabled (default) | Entitlement denied; playback denied |
| Missing / malformed / unknown attrs | Fail closed |

Required Radius **request** attributes today: `User-Name`, `User-Password`, `NAS-Identifier`.

Required entitlement **reply** attribute names (only when mapping enabled): configure `RADIUS_ATTR_PACKAGE` and `RADIUS_ATTR_EXPIRATION` (plus optional branch/status/max-devices).

### Live Radius assumptions (unverified)

- Live SAS Radius authentication is **unverified**
- SAS attribute → package/branch/expiry mapping is **not verified**
- Account-status / entitlement re-query against live SAS is **not implemented**
- **Production rollout is blocked until staging verification is complete**
- Do not claim live SAS verification unless staging-tested

### Production startup gate

Staging/production **fails startup** when:

- `SUBSCRIBER_IDENTITY_MODE=radius` (or live Radius login enabled) **and**
- `RADIUS_ENTITLEMENT_MAPPING_ENABLED=false`

Also fails when mapping is enabled but required attribute names are missing.

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
| Staging | Keep disabled until attribute mapping verified; then enable mapping + Radius carefully |
| Production | Keep **`disabled`** until staging verification is complete — do not enable live Radius yet |

## Deployment configuration

See `app/backend/.env.example`:

- `SUBSCRIBER_IDENTITY_MODE` (default `disabled`)
- `RADIUS_ENTITLEMENT_MAPPING_ENABLED` (default `false`)
- `RADIUS_ATTR_PACKAGE` / `RADIUS_ATTR_EXPIRATION` / optional attrs
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `SUBSCRIBER_MAX_DEVICES_DEFAULT`
- `ENTITLEMENT_CACHE_TTL_SECONDS`
- `ENTITLEMENT_CACHE_GRACE_SECONDS` (default `0` — expired cache never authorizes)
- `RADIUS_*`

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Startup fails on Radius | Mapping disabled in staging/production, or attrs missing |
| 503 on login | Provider unavailable / mode disabled / Radius timeout |
| Entitlement denied after Access-Accept | Expected when mapping disabled or attrs missing |
| 403 `device_limit_exceeded` | Revoke a device via `/api/me/devices` |
| Refresh 401 `refresh_reuse` | Token replay — family revoked; re-login |
