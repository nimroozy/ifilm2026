# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: COMPLETE
A1 LIVE_QA: PASS FOR V1 CONTRACT
A1 CI: PASS
A1 PRODUCTION READY: BLOCKED ONLY ON SECRET ROTATION + STAGING SMOKE
A1 MERGE: WAIT FOR HUMAN APPROVAL
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `db7c96300f0fc4a79a0dfec207f94f0a5b6d92d3`

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**

---

## LIVE_QA client / source matrix (2026-08-19)

Working bearer + dedicated QA subscriber (Kabul). Values never printed.

| Case | Headers | HTTP | success | verified | portal code | customer object |
|------|---------|------|---------|----------|-------------|-----------------|
| **A** | `X-Mobin-Client: ifilm` + `request_source: 3cx_voice` | 200 | true | true | null | yes |
| **B** | `X-Mobin-Client: 3cx-voice-agent` + `request_source: ifilm` | 200 | true | true | null | yes |
| **C** | `X-Mobin-Client: ifilm` + `request_source: ifilm` | 200 | true | true | null | yes |

**Finding:** client header and `request_source` are **not authorization
boundaries** (metadata only). The existing bearer authenticates all three
combinations.

---

## Owner A1 v1 credential decision

Temporary sharing of the Voice AI service bearer between 3CX and iFilm is
**approved for A1 v1**, subject to mandatory credential rotation before
production. This is temporary technical debt.

Long-term A1.1 requirement: dedicated independently revocable iFilm service
credential.

### Committed iFilm metadata defaults (non-secret)

```text
PORTAL_AUTH_ENABLED=false
PORTAL_VOICE_AI_CLIENT=ifilm
PORTAL_REQUEST_SOURCE=ifilm
PORTAL_VOICE_AI_TOKEN=
```

`PORTAL_VOICE_AI_TOKEN` remains backend-secret-only. Never `VITE_*`. Never
log it. Never expose it to the browser. Do not store the new bearer in
repository files.

---

## Credential rotation gate (production enablement BLOCKED)

Owner must confirm all of the following before production:

1. Exposed old Voice AI bearer rotated
2. QA password rotated
3. Portal accepts the new bearer
4. 3CX updated to the new bearer
5. 3CX regression lookup succeeds
6. New bearer installed in iFilm production secret environment (not the repo)

---

## Owner A1 v1 decisions (implemented in code)

### Identity

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{customer_number}
```

Examples: `KBL:1210000`, `NMZ:1210000`.

Missing `customer.customer_number` on a verified success → fail closed (503,
no subscriber row). No username fallback for new portal users.

### Entitlement

```text
success && verified && normalized account_status == "active"
```

`internet_status` does not gate access. Unknown `account_status` → deny.
`expired` → `service_expired`. No invented suspended/disabled codes beyond
generic deny.

### Expiry

No independent `expiry_date` gate. Date kept for display / snapshot.

### Locations

Backend registry is the A1 v1 temporary production source. Frontend production
path fetches `/api/auth/isp/locations` only. Numeric HTML ids rejected at iFilm
login. Portal calls use canonical **name**. Dynamic `/service-locations` is
**A1.1 / tech debt**, not an A1 v1 blocker.

Known A1 v1 locations: Kabul/KBL, Kandahar/KDR, Ghazni/GHZ, Nimruz/NMZ,
Buldak/BLD, Helmand/HLD.

### Invalid credentials

Portal: HTTP 200, `success=true`, `verified=false`, `code=verification_failed`.

iFilm: generic 401 `invalid_credentials` (no account enumeration).

---

## Status

```text
A1 CODE: COMPLETE
A1 LIVE_QA: PASS FOR V1 CONTRACT
A1 PRODUCTION READY: BLOCKED ONLY ON SECRET ROTATION + STAGING SMOKE
A1 MERGE: WAIT FOR HUMAN APPROVAL
```
