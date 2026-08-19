# A1 — Portal Voice AI subscriber authentication (iFilm side)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false` by default.**

This document describes the **current Draft implementation**. Several portal-facing
assumptions are **provisional** pending live portal QA and owner decisions. See
[`A1_PORTAL_AUTH_REPORT.md`](./A1_PORTAL_AUTH_REPORT.md).

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
preferably `GET /api/voice-ai/v1/service-locations`. The backend abstraction must
remain so a dynamic provider can replace the static source **without UI changes**.
Do not duplicate the list in frontend code.

## Identity — PROVISIONAL

Current Draft implementation:

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{internet_username}
```

Codes today: KBL, KDR, GHZ, NMZ, BLD, HLD.

This subject form is **provisional**. Do not claim username is the final stable
identity. Live QA must establish `customer_number` semantics; preferred finals are
`portal_mns:<customer_number>` or `portal_mns:<branch>:<customer_number>` if
branch-scoped. Watchlist / progress / Continue Watching continuity depend on the
stable subject.

Local JWT `sub` remains the integer `subscribers.id`.

Migration `024_portal_subscriber_identity_v1` drops global UNIQUE on
`subscribers.username` so branch-scoped subjects can coexist. Keep 024 in the Draft
PR for review; **do not merge** while the identity contract is unverified.

## Entitlement — PROVISIONAL ONLY

Current Draft rule:

```text
success && verified && customer.account_status == "active"
```

`internet_status` is currently ignored in code — **provisional only**, not proven.
Until live QA documents meanings of `account_status`, `internet_status`, and
`expiry_date`: treat unknown statuses as deny; do not invent enum mappings; do not
assume `account_status=active` alone is sufficient; do not ignore expiry without
documented portal semantics.

No passwordless `/customers/status` yet → **15-minute** entitlement snapshot TTL.
After TTL, new protected playback is denied until re-login. Password is never stored.

## Customer messages

- Invalid credentials: Unable to sign in with the provided Internet account.
- Inactive: Your Internet service is not currently active.
- Portal down: Authentication service is temporarily unavailable. Please try again.
