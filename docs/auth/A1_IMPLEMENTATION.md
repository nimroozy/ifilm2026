# A1 — Portal Voice AI subscriber authentication (iFilm side)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 PORTAL CONTRACT: LIVE_QA + OWNER A1 V1 DECISIONS APPLIED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED (credential + deploy approval)
```

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false` by default.**

See [`A1_PORTAL_AUTH_REPORT.md`](./A1_PORTAL_AUTH_REPORT.md) for LIVE_QA evidence.

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
PORTAL_VOICE_AI_CLIENT=3cx-voice-agent
PORTAL_REQUEST_SOURCE=3cx_voice
PORTAL_CONNECT_TIMEOUT_SECONDS=3
PORTAL_READ_TIMEOUT_SECONDS=5
PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS=900
SUBSCRIBER_IDENTITY_MODE=disabled
```

`PORTAL_VOICE_AI_CLIENT` / `PORTAL_REQUEST_SOURCE` / token are **configurable**. Current
defaults reuse the existing Voice AI / 3CX-shaped headers for development only.

**Not production-approved:** do not treat 3CX credential sharing as the final A1
contract unless the owner explicitly approves temporary sharing, or portal adds a
dedicated iFilm credential (`X-Mobin-Client: ifilm`, dedicated bearer, confirmed
`request_source`).

Never put the token in `VITE_*` or frontend JS. Never commit production secrets.

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

`customer_number` is required on verified success (fail closed; no username
fallback). Same number in Kabul and Nimruz are distinct subjects (`KBL:…` /
`NMZ:…`). No automatic migration of older test rows.

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
