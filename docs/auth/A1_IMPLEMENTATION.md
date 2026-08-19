# A1 — Portal Voice AI subscriber authentication (iFilm side)

```text
A1 CODE: COMPLETE
A1 LIVE_QA: PASS FOR V1 CONTRACT
A1 CI: PASS
A1 PRODUCTION READY: BLOCKED ONLY ON SECRET ROTATION + STAGING SMOKE
A1 MERGE: WAIT FOR HUMAN APPROVAL
```

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false` by default.**

See [`A1_PORTAL_AUTH_REPORT.md`](./A1_PORTAL_AUTH_REPORT.md) for LIVE_QA evidence
and the production rotation gate.

## Routes

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/auth/isp/locations` | Service locations via backend abstraction |
| `POST` | `/api/auth/isp/login` | Branch + Internet username + password → portal lookup → iFilm JWT |

## Portal client (backend only — feature off by default)

```text
PORTAL_AUTH_ENABLED=false
PORTAL_BASE_URL=https://portal.mns.af
PORTAL_VOICE_AI_PREFIX=/api/voice-ai/v1
PORTAL_VOICE_AI_TOKEN=
PORTAL_VOICE_AI_CLIENT=ifilm
PORTAL_REQUEST_SOURCE=ifilm
PORTAL_CONNECT_TIMEOUT_SECONDS=3
PORTAL_READ_TIMEOUT_SECONDS=5
PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS=900
SUBSCRIBER_IDENTITY_MODE=disabled
```

`PORTAL_VOICE_AI_TOKEN` is backend-secret-only. Never `VITE_*`. Never log it.
Never expose it to the browser. Do not store a bearer in repository files.

Owner A1 v1 decision: temporary sharing of the Voice AI service bearer between
3CX and iFilm is approved as **technical debt**, subject to mandatory rotation
before production. A1.1 requires a dedicated independently revocable iFilm
service credential.

LIVE_QA proved `X-Mobin-Client` and `request_source` are not authorization
boundaries. iFilm defaults are `ifilm` / `ifilm` (metadata only).

## Locations — A1 v1 owner-approved temporary registry

Backend `app/services/portal/locations.py` is the single source (Kabul/KBL,
Kandahar/KDR, Ghazni/GHZ, Nimruz/NMZ, Buldak/BLD, Helmand/HLD). Frontend
production UI loads `GET /api/auth/isp/locations` only. Login sends the
canonical **name** to portal. Numeric HTML ids are rejected.

Dynamic `GET /api/voice-ai/v1/service-locations` is **A1.1 / tech debt**
(LIVE_QA 404), not an A1 v1 blocker.

## Identity — A1 v1 (LIVE_QA + owner)

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{customer_number}
```

Examples: `KBL:1210000`, `NMZ:1210000`.

`customer_number` is required on verified success (fail closed; no username
fallback). Same number in Kabul and Nimruz are distinct subjects. No automatic
migration of older test rows.

Local JWT `sub` remains the integer `subscribers.id`.

## Entitlement — A1 v1 (LIVE_QA + owner)

```text
success && verified && customer.account_status == "active"
```

`internet_status` is session online/offline and does **not** gate access.
`expiry_date` is display/snapshot only (no independent gate). Unknown
`account_status` → deny. `expired` → `service_expired`.

No passwordless `/customers/status` yet → **15-minute** entitlement snapshot TTL.
After TTL, new protected playback is denied until re-login. Password is never stored.

## Customer messages

- Invalid credentials: Unable to sign in with the provided Internet account.
- Inactive: Your Internet service is not currently active.
- Portal down: Authentication service is temporarily unavailable. Please try again.
