# A1 — Portal Voice AI subscriber authentication (iFilm side)

**Status:** Implementation for human review  
**Reuse:** `POST https://portal.mns.af/api/voice-ai/v1/customers/lookup`  
**No new portal authenticate endpoint. No separate iFilm portal credential in v1.**

## Routes

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/auth/isp/locations` | Service locations (centralized backend list for A1 v1) |
| `POST` | `/api/auth/isp/login` | Branch + Internet username + password → portal lookup → iFilm JWT |

## Portal client (backend only)

```text
PORTAL_AUTH_ENABLED=true
PORTAL_BASE_URL=https://portal.mns.af
PORTAL_VOICE_AI_PREFIX=/api/voice-ai/v1
PORTAL_VOICE_AI_TOKEN=<existing Voice AI bearer>
PORTAL_VOICE_AI_CLIENT=3cx-voice-agent
PORTAL_REQUEST_SOURCE=3cx_voice
PORTAL_CONNECT_TIMEOUT_SECONDS=3
PORTAL_READ_TIMEOUT_SECONDS=5
PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS=900
SUBSCRIBER_IDENTITY_MODE=portal
```

Headers to portal:

```http
Authorization: Bearer <PORTAL_VOICE_AI_TOKEN>
X-Mobin-Client: 3cx-voice-agent
Content-Type: application/json
```

Never put the token in `VITE_*` or frontend JS.

## Identity

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{internet_username}
```

Codes: KBL, KDR, GHZ, NMZ, BLD, HLD.

Local JWT `sub` remains the integer `subscribers.id` (watchlist / CW / progress).

Migration `024_portal_subscriber_identity_v1` drops global UNIQUE on `subscribers.username` so the same Internet username can exist in two branches.

## Entitlement

Allow when portal returns:

```text
success && verified && customer.account_status == "active"
```

`internet_status` (online/offline) is **ignored** for access.

No passwordless `/customers/status` yet → **15-minute** entitlement snapshot TTL. After TTL, new protected playback is denied until re-login. Password is never stored.

## Customer messages

- Invalid credentials: Unable to sign in with the provided Internet account.
- Inactive: Your Internet service is not currently active.
- Portal down: Authentication service is temporarily unavailable. Please try again.
