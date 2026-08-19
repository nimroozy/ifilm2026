# A1 — Portal Voice AI subscriber authentication (iFilm side)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: LIVE_QA PARTIAL — SUCCESS PATH CAPTURED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON OWNER DECISIONS (credential + identity + locations)
```

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false` by default.**

This document describes the **current Draft implementation**. Authenticated LIVE_QA
evidence is in [`A1_PORTAL_AUTH_REPORT.md`](./A1_PORTAL_AUTH_REPORT.md). Code was
**not** changed to match QA; owner review first.

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

## Locations — temporary static fallback

`GET /api/auth/isp/locations` is served from a **centralized backend** static list
(test/fallback only). Production A1 still requires a dynamic portal JSON source,
preferably `GET /api/voice-ai/v1/service-locations` (**LIVE_QA 404**). The backend
abstraction must remain so a dynamic provider can replace the static source
**without UI changes**. Do not duplicate the list in frontend code.

S2S lookup accepts **name or code** (`Kabul`/`KBL`), not HTML numeric ids (**LIVE_QA**).

## Identity — LIVE_QA: branch-scoped `customer_number`

Current Draft implementation (unchanged):

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{internet_username}
```

**LIVE_QA:** `customer_number` is a string and is **not globally unique** (same
number in Kabul and Nimruz). Preferred contract after owner approval:

```text
external_subject = {BRANCH_CODE}:{customer_number}
```

For the QA subscriber, username == customer_number, so current subjects
(`KBL:1210000`, `NMZ:1210000`) already match. **Do not auto-migrate.** Never key
on username or `customer_number` alone.

Local JWT `sub` remains the integer `subscribers.id`.

Migration `024_portal_subscriber_identity_v1` stays in Draft for review.

## Entitlement — LIVE_QA supports current rule; code unchanged

Current Draft rule (unchanged):

```text
success && verified && customer.account_status == "active"
```

**LIVE_QA:** `account_status` is subscription state (`active` / `expired`).
`internet_status=offline` on **both** active and expired → session state, ignore
for entitlement. `expiry_date` is `YYYY-MM-DD` and aligned with `account_status`
on the two tested accounts — no extra expiry gate added. Suspended / other
statuses untested; unknown remains deny.

No passwordless `/customers/status` yet → **15-minute** entitlement snapshot TTL.
After TTL, new protected playback is denied until re-login. Password is never stored.

## Customer messages

- Invalid credentials: Unable to sign in with the provided Internet account.
- Inactive: Your Internet service is not currently active.
- Portal down: Authentication service is temporarily unavailable. Please try again.
