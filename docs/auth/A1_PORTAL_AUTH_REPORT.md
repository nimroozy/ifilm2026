# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: LIVE_QA PARTIAL — SUCCESS PATH CAPTURED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON OWNER DECISIONS (credential + identity + locations)
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `441403449fbf98d3245efd01950635fc29862bcc`

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**  
**Do not start G3 / T1 / player redesign.**  
**Application behavior was not changed in this pass.**

Classification key:

| Tag | Meaning |
|-----|---------|
| **LIVE_QA** | Observed against production portal in this authenticated pass |
| **PRIOR_3CX** | Historical 3CX notes (superseded where LIVE_QA exists) |
| **PROVISIONAL** | Still not fully proven / owner decision required |

**Security:** A service bearer and QA subscriber password were pasted into chat. Rotate
both after this pass. This document contains **no** secret values (no bearer, no
password, no Authorization header).

QA-only used `X-Mobin-Client: 3cx-voice-agent` and `request_source: 3cx_voice`.
That does **not** approve shared 3CX credentials for production iFilm.

---

## LIVE_QA authenticated matrix (2026-08-19)

`POST https://portal.mns.af/api/voice-ai/v1/customers/lookup`

### 1. Successful lookup HTTP + structure (**LIVE_QA**)

- **HTTP status:** `200`
- **Envelope (nested — do not flatten):** `success` (bool), `verified` (bool), `customer` (object)
- **No** top-level `code` / `message` on success

### 2–3. Redacted success payloads + identity (**LIVE_QA**)

Same Internet username + password resolved **two different branch-scoped customers**
with the **same** `customer_number`.

**Kabul (QA-declared branch) — expired:**

```json
{
  "success": true,
  "verified": true,
  "customer": {
    "display_name": "<REDACTED>",
    "customer_number": "1210000",
    "branch": "Kabul",
    "account_status": "expired",
    "internet_status": "offline",
    "current_package": {
      "name": "L3 | 250GB | 12 Mbps |1Month",
      "download_speed": "12 Mbps",
      "upload_speed": ""
    },
    "expiry_date": "2026-08-09",
    "days_remaining": -10,
    "balance_due": 0,
    "currency": "AFN"
  }
}
```

**Nimruz (same username + password, other branch) — active:**

```json
{
  "success": true,
  "verified": true,
  "customer": {
    "display_name": "<REDACTED>",
    "customer_number": "1210000",
    "branch": "Nimruz",
    "account_status": "active",
    "internet_status": "offline",
    "current_package": {
      "name": "L1-85 GB | 3Mbps | 1Month",
      "download_speed": "3 Mbps",
      "upload_speed": ""
    },
    "expiry_date": "2026-08-23",
    "days_remaining": 4,
    "balance_due": 600,
    "currency": "AFN"
  }
}
```

Field types (**LIVE_QA**):

| Field | Type |
|-------|------|
| `success` | bool |
| `verified` | bool |
| `customer.customer_number` | **string** (`"1210000"`) |
| `customer.branch` | string (canonical name, e.g. `"Kabul"`, `"Nimruz"`) |
| `customer.account_status` | string |
| `customer.internet_status` | string |
| `customer.current_package` | object `{name, download_speed, upload_speed}` (strings) |
| `customer.expiry_date` | string `YYYY-MM-DD` |
| `customer.days_remaining` | int (can be **negative**) |
| `customer.balance_due` | int |
| `customer.currency` | string (`AFN`) |

`customer_number` **equals** the Internet username for this QA subscriber in **both**
branches. It is **not globally unique**: Kabul and Nimruz both return `"1210000"` with
different package, expiry, balance, and `account_status`.

**Identity recommendation (LIVE_QA):**

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{customer_number}
```

Examples: `KBL:1210000`, `NMZ:1210000`.

Do **not** use `customer_number` alone. Current `{BRANCH_CODE}:{username}` is
**value-equivalent** for this QA account (username == customer_number) but the
stable documented key should be **`customer_number`**, branch-scoped. **Do not
auto-migrate** existing test rows until owner approves.

Kandahar / Ghazni / Buldak / Helmand + same username/password →
`verification_failed` (no third copy of this number in those branches).

### 4–8. Entitlement semantics (**LIVE_QA**)

Observed `account_status` values: **`active`**, **`expired`**.

Observed `internet_status` values: **`offline`** only (on **both** active and expired).

| Signal | Meaning from these two live accounts |
|--------|--------------------------------------|
| `account_status` | Subscription / service eligibility (`active` vs `expired`) |
| `internet_status` | **Session online/offline**, **not** entitlement. Active Nimruz is `offline`. |
| `expiry_date` | Calendar date `YYYY-MM-DD`. Kabul `2026-08-09` + `days_remaining=-10` + `expired`. Nimruz `2026-08-23` + `days_remaining=4` + `active`. |
| Independent expiry gate? | **Not required** given these samples: `account_status` already tracks expiry. Keep fail-closed on unknown statuses. Do not invent extra enums. |

**Current code** `success && verified && account_status == "active"` (ignore
`internet_status`):

- Would **deny** Kabul expired — **correct** vs LIVE_QA
- Would **allow** Nimruz active while `internet_status=offline` — **correct** vs LIVE_QA
- Maps `expired` to deny — **correct** vs LIVE_QA

**Entitlement mapping change required now?** **No** for observed values. Suspended /
other statuses remain **untested**. Unknown still deny. **Do not change code** until
owner review.

### 9. Accepted branch representation (**LIVE_QA**)

`/customers/lookup` `branch` field:

| Sent | Result |
|------|--------|
| `Kabul` | success → `customer.branch=Kabul` |
| `kabul` | success → Kabul |
| `KBL` | success → Kabul |
| `Nimruz` | success → Nimruz (different customer) |
| `NMZ` | success → Nimruz |
| `1` / `2` (HTML numeric ids) | `verification_failed` — **not accepted** |
| `Kandahar`, `Ghazni`, `Buldak`, `Helmand` (no matching account) | `verification_failed` |
| `NotACity` | `verification_failed` |
| empty `branch` | HTTP **400** `validation_failed` |

Accepted S2S form: **canonical name or branch code**, not HTML numeric id.

`GET /api/voice-ai/v1/service-locations` remains **404**. Static six-name backend
list is still **not** authoritative production config.

### 10–12. Error behavior (**LIVE_QA**)

All customer-validation failures below used a valid service bearer.

| Case | HTTP | Body |
|------|------|------|
| Wrong password | **200** | `success=true`, `verified=false`, `code=verification_failed`, `message=The customer information could not be verified.` — **no customer object** |
| Invalid username | **200** | **identical** to wrong password |
| Unknown / unmatched branch | **200** | **identical** `verification_failed` |
| Empty branch | **400** | `success=false`, `code=validation_failed` |
| Missing/`Authorization` without `Bearer` / `X-Api-Key` / `X-Mobin-Token` | **401** | `success=false`, `code=unauthorized`, `message=Invalid or missing service token.` |

Wrong password and invalid username are **indistinguishable**. iFilm must keep a
**generic** customer-facing error (no enumeration).

**Wrong branch is not a dedicated error** when the same username/password exists
in another SAS branch: lookup **succeeds** as that other branch’s customer.

### 13. Inactive / expired / suspended

- **Expired:** **TESTED** — Kabul `account_status=expired` (above).
- **Suspended:** **NOT TESTED** (no suspended QA account).

### Extra LIVE_QA (service client header)

`Authorization: Bearer <token>` + `X-Mobin-Client: ifilm` also returned HTTP 200
for the Kabul lookup. That proves the **current** bearer is not strictly bound to
the `3cx-voice-agent` string. It does **not** approve production sharing or replace
a dedicated iFilm credential/owner decision.

`GET /agent/config` with the same bearer: HTTP **503** `dependency_unavailable`
(not a location source).

---

## Required findings (answered)

| # | Question | LIVE_QA answer |
|---|----------|----------------|
| 1 | Success JSON structure | Nested `{success, verified, customer:{...}}`; HTTP 200 |
| 2 | Exact `customer_number` | string `"1210000"` (same as username here) |
| 3 | Stable identity? | Branch-scoped only — **not** globally unique |
| 4 | Exact `account_status` | `active`, `expired` |
| 5 | Exact `internet_status` | `offline` (only value seen) |
| 6 | `expiry_date` | `YYYY-MM-DD`; `days_remaining` int, may be negative |
| 7 | `internet_status` meaning | **Session online/offline**, not entitlement |
| 8 | Independent expiry gate? | **No** on these samples (`account_status` already expired/active) |
| 9 | Accepted branch | **Name or code** (`Kabul`/`KBL`, `Nimruz`/`NMZ`); **not** numeric id |
| 10 | Invalid password | HTTP 200 `verification_failed` (generic) |
| 11 | Invalid username | Same as invalid password |
| 12 | Wrong branch | Either other-branch success **or** same `verification_failed` |
| 13 | Inactive/suspended | Expired **yes**; suspended **no** |
| 14 | Change entitlement code? | **Not now** — current active-only + ignore `internet_status` matches evidence |
| 15 | Change `{branch}:{username}`? | **Document** preferred `{branch_code}:{customer_number}`; **do not migrate yet** (values coincide here) |

---

## Still blocking production / merge

1. Owner decision: dedicated iFilm credential vs explicit temporary 3CX share.
2. Dynamic `GET /service-locations` still missing (**404**).
3. Identity contract approval + no auto-migration.
4. Suspended / other `account_status` values untested.
5. Rotate chat-exposed token and QA password.
6. Keep `PORTAL_AUTH_ENABLED=false`. No deploy.

---

## Status (authoritative)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: LIVE_QA PARTIAL — SUCCESS PATH CAPTURED
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON OWNER DECISIONS (credential + identity + locations)
```
