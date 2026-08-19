# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — SUPPLIED SERVICE TOKEN REJECTED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `84496ab9c67d17f25ca525c15d7a1e317ec7135e`

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**  
**Do not start G3 / T1 / player redesign.**

Classification key:

| Tag | Meaning |
|-----|---------|
| **LIVE_QA** | Observed against production portal in this agent pass |
| **PRIOR_3CX** | Historical 3CX integration evidence |
| **PROVISIONAL** | Implementation assumption — not proven by authenticated success |

**Security note (owner action):** A service bearer and QA subscriber password were pasted into
chat for this pass. Treat both as **compromised for sharing channels**. Rotate the portal
Voice AI service token and the QA subscriber password after QA. Never commit secrets to the
repo. This document contains **no** secret values.

---

## LIVE_QA authenticated attempt (2026-08-19)

### What was attempted

`POST https://portal.mns.af/api/voice-ai/v1/customers/lookup` with:

- `X-Mobin-Client: 3cx-voice-agent`
- `request_source: 3cx_voice`
- `Authorization: Bearer <supplied token>` (value never logged/committed)
- QA branch / username / password from owner (values never committed)

Also probed alternate auth header forms (token-only Authorization, `X-Api-Key`,
`X-Mobin-Token`, client header variants, `GET /agent/config`). **All** returned the same
service-auth failure.

### LIVE_QA result — service credential

| Observation | Value | Tag |
|-------------|-------|-----|
| HTTP status | **401** | **LIVE_QA** |
| Body | `{"success":false,"code":"unauthorized","message":"Invalid or missing service token."}` | **LIVE_QA** |
| Matches missing/fake bearer behavior? | **Yes** (identical) | **LIVE_QA** |
| Supplied token shape (non-secret) | length **64**, lowercase hex charset | **LIVE_QA** |
| Subscriber lookup body reached? | **No** — rejected before customer validation | **LIVE_QA** |

**Implication:** The string provided as `PORTAL_VOICE_AI_TOKEN` is **not accepted** by
portal Voice AI middleware as a live service bearer. Authenticated customer-matrix items
(success JSON, statuses, identity, wrong-password, etc.) **cannot** be measured until a
**working** service token is supplied.

Hypothesis (not proven): a 64-char hex string may be a **hash** of a Sanctum/plain token
rather than the plaintext token 3CX actually sends. Portal likely expects the **plaintext**
service token (often Laravel Sanctum-style), not a SHA-256 digest.

### LIVE_QA matrix status

| Case | Status |
|------|--------|
| Active subscriber lookup | **BLOCKED** — service token rejected |
| Invalid password | **BLOCKED** — same |
| Invalid username | **BLOCKED** — same |
| Wrong branch | **BLOCKED** — same |
| Branch as numeric id (`1`) / code (`KBL`) | **BLOCKED** — same (cannot evaluate acceptance) |
| Inactive/suspended | **NOT TESTED** (no valid service auth; no optional QA accounts used) |

### Unauthenticated / structural LIVE_QA (unchanged)

| Call | HTTP | Tag |
|------|------|-----|
| `GET /service-locations` | **404** | **LIVE_QA** |
| Lookup without/fake bearer | **401** unauthorized | **LIVE_QA** |

HTML login branch select (not S2S authority): Kabul=`1`, Nimruz=`2`, Kandahar=`3`,
Ghazni=`4`, Helmand=`5`, Buldak=`6` (**LIVE_QA**).

---

## Required findings (still open)

| # | Question | Status |
|---|----------|--------|
| 1 | Exact successful lookup JSON structure | **NOT CAPTURED** |
| 2 | Exact `customer_number` | **UNKNOWN** |
| 3 | `customer_number` suitable as stable identity? | **UNKNOWN** |
| 4 | Exact `account_status` | **UNKNOWN** |
| 5 | Exact `internet_status` | **UNKNOWN** |
| 6 | Exact `expiry_date` value/format | **UNKNOWN** |
| 7 | Is `internet_status` session online/offline or entitlement? | **UNKNOWN** |
| 8 | Must `expiry_date` independently gate iFilm? | **UNKNOWN** |
| 9 | Exact accepted branch representation | **UNKNOWN** |
| 10 | Invalid password behavior | **NOT TESTED** |
| 11 | Invalid username behavior | **NOT TESTED** |
| 12 | Wrong branch behavior | **NOT TESTED** |
| 13 | Inactive/suspended behavior | **NOT TESTED** |
| 14 | Must entitlement mapping change? | **UNPROVEN** — **do not change code** |
| 15 | Must `{branch}:{username}` identity change? | **UNPROVEN** — **do not migrate** |

Application behavior: **unchanged**.

---

## What owner must supply next

1. **Rotate** the chat-exposed service token and QA password.
2. Provide the **working plaintext** Voice AI / 3CX service bearer that currently authenticates
   `POST /api/voice-ai/v1/customers/lookup` in production 3CX (prefer Cursor secure env /
   linked environment secrets — avoid pasting into chat again).
3. Confirm QA subscriber branch/username/password still valid after password rotation.
4. Re-run authenticated LIVE_QA.

Until a bearer is accepted (HTTP ≠ 401 `unauthorized` for service token), customer entitlement
and identity questions remain **PROVISIONAL**.

---

## Status (authoritative)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — SUPPLIED SERVICE TOKEN REJECTED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```
