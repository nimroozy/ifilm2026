# Live contract — `https://portal.mns.af/api/voice-ai/v1`

**Date:** 2026-08-18  
**Correction:** The first A1 audit searched `/api/integrations/ifilm/*` and concluded portal had no S2S API. That namespace is empty. **This** namespace is the existing partner API (built for the 3CX voice agent).

**Evidence classes**

| Class | Meaning |
|-------|---------|
| **LIVE** | Observed against production portal in this pass (no valid service token used) |
| **PRIOR_3CX** | Shape/behavior from the original 3CX portal integration (not re-fetched with a live token this pass) |
| **UNKNOWN** | Requires a dedicated iFilm credential and/or QA subscriber |

No real 3CX bearer token, no customer password, and no service secret appears in this document.

---

## 1. Base URL and discovered routes

**Base:** `https://portal.mns.af/api/voice-ai/v1`

| Method | Path | LIVE result |
|--------|------|-------------|
| `GET` | `/agent/config` | **Exists.** Unauthenticated → `401` JSON `unauthorized`. **PRIOR_3CX:** remote voice-agent prompt/config — **not** a location source |
| `POST` | `/customers/lookup` | **Exists.** `GET`/`PUT` → `405` “Supported methods: POST.” Unauthenticated POST → `401` `unauthorized` |
| `POST` | `/packages/search` | **Exists.** Unauthenticated POST → `401` `unauthorized` |
| `GET` | `/service-locations` | **404** — not present |
| `GET` | `/branches`, `/locations`, `/provinces` | **404** |
| `POST`/`GET` | `/customers/status`, `/customers/validate`, `/customers/entitlement` | **404** |
| `POST` | `/auth/validate`, `/token` | **404** |
| `GET` | `/health`, `/openapi.json`, `/schema`, `/clients` | **404** |
| `GET` | `/api/voice-ai/v2/*` | **404** |

Laravel route-not-found vs method-not-allowed is how existence was proven without a token.

---

## 2. Partner authentication (LIVE)

Required:

```http
Authorization: Bearer <service token>
Accept: application/json
Content-Type: application/json   # POST only
```

PRIOR_3CX client header (CORS preflight **LIVE** allows it):

```http
X-Mobin-Client: 3cx-voice-agent
Authorization: Bearer <3CX service token>
```

Desired iFilm end state (capability **not proven**; may need a small portal middleware change):

```http
X-Mobin-Client: ifilm
Authorization: Bearer <separate IFILM_PORTAL_TOKEN>
```

### LIVE unauthorized body

```json
{
  "success": false,
  "code": "unauthorized",
  "message": "Invalid or missing service token."
}
```

Observed for:

- missing `Authorization`
- `Authorization: Bearer` with a non-secret fake value
- fake bearer + `X-Mobin-Client: ifilm`
- fake bearer + `X-Mobin-Client: 3cx-voice-agent`
- fake bearer + `X-Client-Id: ifilm` (this header is **not** a substitute)
- `X-Mobin-Client` alone (no bearer)

**Implication:** a service bearer exists and is mandatory. The client header does not bypass it.

**Token-model uncertainty:** PRIOR_3CX proves **one** working service token. It does **not** prove portal already supports multiple client-specific tokens. Middleware may currently accept a single global secret. Independent iFilm credentials are still **required**; portal must **verify** multi-client support and **extend** auth middleware if only one global token is accepted.

There is no public `/token` or `/clients` endpoint (**LIVE** 404).

**Do not configure iFilm with the 3CX `MOBIN_PORTAL_AI_TOKEN`.**

### Token scopes (UNKNOWN)

No scope document or introspect endpoint is public. Whether an iFilm credential can be limited to lookup + locations (and denied `packages/search` / `agent/config`) is a portal-admin question.

---

## 3. CORS / browser access (LIVE)

This API is usable as S2S, but CORS is currently **permissive**:

| Header | Observed |
|--------|----------|
| `Access-Control-Allow-Origin` | `*` (including `Origin: https://ifilm.af` and arbitrary origins) |
| `Access-Control-Allow-Methods` | `GET` on `/agent/config`; `POST` on `/customers/lookup` |
| `Access-Control-Allow-Headers` | `authorization,x-mobin-client,content-type` |
| OPTIONS | `204` |

iFilm **must not** put the service token in frontend JS. Browser callers with a leaked token would succeed CORS-wise. Portal should treat this as defense-in-depth debt; iFilm still keeps the token backend-only.

---

## 4. Rate limiting (LIVE, unauthenticated)

Authenticated responses were not observed.

Unauthenticated `/agent/config` and `/customers/lookup` return:

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: <decrementing>
Cache-Control: no-store, private
```

This matches Laravel’s default 60/min throttle. Per-client, per-username, or authenticate-specific limits are **UNKNOWN**. HTTP `429` was not produced in this light probe (not exhausted).

---

## 5. `GET /agent/config` — remote voice-agent configuration (NOT locations)

**LIVE:** route exists; body not observed this pass (token required).

**PRIOR_3CX:** this is a **remote AI-agent prompt/config** endpoint. Expected success shape (approximate):

```json
{
  "success": true,
  "version": "...",
  "instructions": "..."
}
```

**Do not assume `/agent/config` supplies service locations.** It is not a confirmed location source. iFilm should not call it for the login location dropdown.

**LIVE 404:** no dedicated `/service-locations`, `/branches`, `/locations`, or `/provinces` under `/voice-ai/v1`.

Known customer-facing branch **names** from portal HTML + PRIOR_3CX (bootstrap evidence only — **do not hard-code** as iFilm’s long-term source):

- Kabul
- Kandahar
- Ghazni
- Nimruz
- Buldak
- Helmand

Because no existing JSON locations endpoint has been found, the **minimal portal addition** is:

```http
GET /api/voice-ai/v1/service-locations
```

Preferred shape (use actual portal fields when implemented; never include SAS hosts/secrets):

```json
{
  "success": true,
  "locations": [
    {
      "id": "1",
      "name": "Kabul",
      "active": true
    }
  ]
}
```

Do **not** invent `/api/integrations/ifilm/*`.

---

## 6. `POST /customers/lookup` — subscriber authentication

**LIVE:** route exists; POST-only; token required before body validation.

Still **UNKNOWN** until a dedicated iFilm credential + QA lookup:

- whether portal accepts any `request_source` other than `3cx_voice`
- whether `branch` accepts names only, or also numeric `branch_id` (`1`)
- exact `account_status` / `internet_status` enum values
- username case normalization
- username collision across branches
- `customer_number` global uniqueness

### PRIOR_3CX request shape

```json
{
  "branch": "Kabul",
  "username": "<internet username>",
  "password": "<internet password>",
  "request_source": "3cx_voice"
}
```

**Confirmed `request_source`:** `"3cx_voice"` only.

**iFilm `request_source` remains UNKNOWN.** Do **not** assume `"ifilm"` until portal accepts or documents it.

### PRIOR_3CX success shape (nested — do not flatten)

Envelope: `success`, `verified`.  
Subscriber/service fields live under `customer`.  
`current_package` is an **object**, not a string.

```json
{
  "success": true,
  "verified": true,
  "customer": {
    "display_name": "...",
    "customer_number": "...",
    "branch": "Kabul",
    "account_status": "...",
    "internet_status": "...",
    "current_package": {
      "name": "...",
      "download_speed": "...",
      "upload_speed": "..."
    },
    "expiry_date": "...",
    "days_remaining": 10
  }
}
```

Do **not** build frontend/backend DTOs from a flattened `{ display_name, customer_number, ... }` payload.

Exact string values/enums still require a real QA lookup.

### PRIOR_3CX validation errors (do not show to iFilm customers)

The 3CX client handled HTTP **400/422**-style validation failures including:

| Code | Meaning (portal/3CX) |
|------|----------------------|
| `invalid_branch` | Branch not accepted |
| `branch_rejected` | Branch rejected |
| `username_rejected` | Username rejected |
| `password_rejected` | Password rejected |

iFilm must **not** surface these distinctions. Customer-facing credential failures stay generic (invalid location / username / password). Logs may store the portal `code` only.

### Proposed iFilm mapping (UNVERIFIED — confirm with QA)

Login / playback entitlement should require:

1. Envelope `success == true` and `verified == true`
2. Internet service is usable — derive from **actual** `customer.internet_status` / `customer.account_status` / `customer.expiry_date` after a successful QA lookup
3. Fail closed if those fields are missing or unrecognized

Likely denied (names only, not confirmed):

- suspended / disabled account
- expired internet
- `verified=false`

Do **not** ship this mapping as production truth until a dedicated QA account returns a real payload.

---

## 7. Stable identity (UNKNOWN until QA)

Preferred if `customer_number` is globally unique across SAS branches:

```text
provider = portal_mns
external_subject = <customer_number>
```

If `customer_number` is only unique **inside** a branch (same number or username can exist in Kabul and Kandahar):

```text
external_subject = {canonical_branch}:{customer_number}
```

Never key iFilm identity on username alone.

**iFilm code note (for the implementation pass):** `upsert_subscriber_from_identity` currently also matches `Subscriber.username` globally. Same Internet username in two locations would collide unless that lookup becomes `(provider, external_subject)` first.

---

## 8. Passwordless revalidation (LIVE: absent)

Searched existing `/voice-ai/v1` surface for:

- customer status without password
- signed assertion
- entitlement/validate/token endpoints

**None exist (404).**

`/customers/lookup` requires `password` in the 3CX request concept. There is no safe existing method for iFilm to re-check “still active” without the Internet password.

Recommended **minimal** portal addition (optional for v1 only if product accepts bounded entitlement TTL + forced re-login):

```http
POST /api/voice-ai/v1/customers/status
```

```json
{
  "branch": "Kabul",
  "customer_number": "<stable id>"
}
```

No password. No assertion store on iFilm. Portal re-queries current SAS/service state.

Until that exists, iFilm may use a **bounded local entitlement TTL** and fail closed on new protected playback after expiry (re-login required). Do not persist the password to fake validate.

---

## 9. `POST /packages/search`

**LIVE:** exists; token required. Not needed for A1 login/entitlement. Do not call it from iFilm unless a later product need appears. Prefer scoping the iFilm token away from it if portal supports scopes.

---

## 10. Suitability for a non-3CX server consumer

| Question | Answer |
|----------|--------|
| Is this a real S2S JSON API (not CSRF/session)? | **Yes (LIVE)** |
| Can iFilm reuse `/customers/lookup` for password verify? | **Likely yes (OPERATOR + LIVE route)** — confirm with iFilm token + QA |
| Does it require 3CX-specific signaling? | **No evidence** it is more than HTTP JSON + bearer |
| Can iFilm share the 3CX token? | **No** |
| Does portal already support multiple client tokens? | **UNKNOWN** — PRIOR_3CX proves one bearer; middleware may be global |
| Locations API confirmed? | **No** — `/agent/config` is voice-agent prompt/config, not locations |
| Passwordless status API? | **No (LIVE 404)** |
| Safe for production iFilm enablement today? | **No** — see §12 blockers |

---

## 11. Security rules for iFilm (unchanged)

- Browser → `ifilm.af` only
- iFilm backend → `https://portal.mns.af/api/voice-ai/v1` only
- Never store or log password, bearer token, or client secret
- Never send password to OpenAI or put it in stream tokens
- Never connect iFilm to SAS DBs
- Never reuse `MOBIN_PORTAL_AI_TOKEN`
- Logs may include: `client=ifilm`, branch, success/failure, stable customer id, portal validation `code`
- Never show `invalid_branch` / `username_rejected` / `password_rejected` to customers

---

## 12. Portal additions now required (small; reuse lookup)

Do **not** build another authenticate endpoint.

| # | Change | Required for A1 impl? |
|---|--------|------------------------|
| A | Dedicated iFilm service credential (`X-Mobin-Client: ifilm` + separate bearer). Extend middleware if only one global token exists today. | **Yes** |
| B | `GET /api/voice-ai/v1/service-locations` | **Yes** (no existing JSON location source) |
| C | `POST /api/voice-ai/v1/customers/status` (branch + `customer_number`, no password) | Optional if product accepts TTL + re-login |

Reuse existing: `POST /api/voice-ai/v1/customers/lookup`.

### A1 implementation blockers (before iFilm login code)

1. Dedicated iFilm portal credential
2. Service-locations JSON endpoint (or another **real** dynamic source — not `/agent/config`, not a hard-coded list)
3. One successful QA `POST /customers/lookup`
4. Confirmed `customer_number` identity semantics
5. Confirmed `account_status` / `internet_status` values
6. Confirmed `request_source` accepted for iFilm

Passwordless status may be deferred only with an explicit TTL/re-login policy.
