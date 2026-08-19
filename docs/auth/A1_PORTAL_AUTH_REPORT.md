# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: pending this tip
A1 PORTAL CONTRACT: LIVE_QA + OWNER A1 V1 DECISIONS APPLIED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED (credential rotation / dedicated iFilm token + deploy approval)
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** _(stamped in tip commit)_  

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**

---

## LIVE_QA client / source matrix (2026-08-19)

Working bearer + dedicated QA subscriber (Kabul). Values never printed.

| Case | Headers | HTTP | success | verified | portal code | customer object |
|------|---------|------|---------|----------|-------------|-----------------|
| **A** | `X-Mobin-Client: ifilm` + `request_source: 3cx_voice` | 200 | true | true | null | yes |
| **B** | `X-Mobin-Client: 3cx-voice-agent` + `request_source: ifilm` | 200 | true | true | null | yes |
| **C** | `X-Mobin-Client: ifilm` + `request_source: ifilm` | 200 | true | true | null | yes |

**Finding:** client header and `request_source` are **not enforced** (metadata only).
The existing bearer authenticates all three combinations.

### Recommended portal headers (not applied as defaults)

**Preferred (not implemented; needs portal-issued dedicated secret):**

```text
Authorization: Bearer <dedicated iFilm token>
X-Mobin-Client: ifilm
request_source: ifilm
```

**Current code defaults (unchanged):** `3cx-voice-agent` / `3cx_voice` + shared Voice AI
bearer env var.

Temporary shared bearer for A1 v1 is **not assumed approved**. If owner later
approves after **rotation** (token was exposed in chat): backend secret only, never
`VITE_*`, never logged, `PORTAL_AUTH_ENABLED=false` until deploy approval, and
record independently revocable iFilm credential as tech debt.

---

## Owner A1 v1 decisions (implemented in code)

### Identity

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{customer_number}
```

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

### Invalid credentials

`verification_failed` (bad user or bad password) → same generic 401
`invalid_credentials`.

---

## Status

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 PORTAL CONTRACT: LIVE_QA + OWNER A1 V1 DECISIONS APPLIED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED
```
