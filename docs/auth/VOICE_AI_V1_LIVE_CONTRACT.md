# Live contract — `https://portal.mns.af/api/voice-ai/v1`

**Date:** 2026-08-18  
**Correction:** The first A1 audit searched `/api/integrations/ifilm/*` and concluded portal had no S2S API. That namespace is empty. **This** namespace is the existing partner API (built for the 3CX voice agent).

**Evidence classes**

| Class | Meaning |
|-------|---------|
| **LIVE** | Observed against production portal in this pass (no valid service token used) |
| **OPERATOR** | Provided by the portal/3CX operators; not independently confirmed in this pass |
| **UNKNOWN** | Requires a dedicated iFilm token and/or QA subscriber |

No real 3CX bearer token, no customer password, and no service secret appears in this document.

---

## 1. Base URL and discovered routes

**Base:** `https://portal.mns.af/api/voice-ai/v1`

| Method | Path | LIVE result |
|--------|------|-------------|
| `GET` | `/agent/config` | **Exists.** Unauthenticated → `401` JSON `unauthorized` |
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

Operator-documented client header (CORS preflight **LIVE** allows it):

```http
X-Mobin-Client: 3cx-voice-agent
```

Desired iFilm client (not issued in this environment):

```http
X-Mobin-Client: ifilm
Authorization: Bearer <IFILM_PORTAL_TOKEN>
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

**Implication:** the client header does not bypass the token. A separate iFilm identity is plausible (`X-Mobin-Client` is a first-class CORS-allowed header) but **cannot be self-issued**. There is no public `/token` or `/clients` endpoint.

**Do not configure iFilm with the 3CX `MOBIN_PORTAL_AI_TOKEN`.** Issue a distinct `IFILM_PORTAL_TOKEN` on portal.

### Token scopes (UNKNOWN)

No scope document or introspect endpoint is public. Whether `ifilm` can be limited to lookup+config (and denied `packages/search`) is a portal-admin question.

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

## 5. `GET /agent/config` — location source candidate

**LIVE:** route exists; body not observed (token required).

**OPERATOR:** this is the 3CX agent configuration endpoint. It **may** include branches / provinces / supported location names. That is the first place iFilm must look for dynamic locations.

**LIVE 404:** no dedicated `/service-locations`, `/branches`, `/locations`, or `/provinces` under `/voice-ai/v1`.

Until `/agent/config` is read with an iFilm token:

- Do **not** treat HTML `/login` options as the long-term locations API.
- HTML branches (Kabul, Nimruz, Kandahar, Ghazni, Helmand, Buldak) remain **bootstrap evidence only**.

If `/agent/config` does **not** list customer-facing locations, the **only** recommended portal addition is:

```http
GET /api/voice-ai/v1/service-locations
```

Do **not** invent `/api/integrations/ifilm/*`.

---

## 6. `POST /customers/lookup` — subscriber authentication

**LIVE:** route exists; POST-only; token required before body validation.

Therefore these are **UNKNOWN** until an iFilm token exists:

- allowed `request_source` values (`ifilm` vs `3cx_voice` vs free text)
- whether `branch` accepts names only, or also numeric `branch_id` (`1`)
- success HTTP status and JSON schema
- failure codes for bad password vs inactive service
- username case normalization
- username collision across branches

### OPERATOR request shape (3CX)

```json
{
  "branch": "Kabul",
  "username": "<internet username>",
  "password": "<internet password>",
  "request_source": "3cx_voice"
}
```

### Conceptual iFilm request (do not invent `request_source` if portal enumerates it)

```json
{
  "branch": "Kabul",
  "username": "1210000",
  "password": "<transient>",
  "request_source": "ifilm"
}
```

Use the exact `request_source` portal accepts. Confirm with a token; do not guess if lookup 422s.

### OPERATOR known branch names

- Kabul
- Nimruz
- Kandahar
- Ghazni
- Helmand
- Buldak

These match the HTML `/login` labels. Prefer names from `/agent/config` when confirmed.

### OPERATOR success fields (names only — values/enums not live-verified)

| Field | Notes |
|-------|--------|
| `success` | Envelope |
| `verified` | Password/account verification flag — **do not treat HTTP 200 alone as entitlement** |
| `display_name` | Customer display name |
| `customer_number` | Candidate stable id — uniqueness **UNKNOWN** |
| `branch` | Location name used for lookup |
| `account_status` | Exact enum **UNKNOWN** |
| `internet_status` | Exact enum **UNKNOWN** |
| `current_package` | Package label |
| `expiry_date` | Service expiry; format **UNKNOWN** |
| `days_remaining` | Convenience field; do not prefer over `expiry_date` |

### Proposed iFilm mapping (UNVERIFIED — confirm with QA)

Login / playback entitlement should require:

1. `verified` is true (boolean or portal-equivalent)
2. Internet service is usable — derive from **actual** `internet_status` / `account_status` / `expiry_date` after a successful QA lookup
3. Fail closed if any of those fields are missing or unrecognized

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

This is the **only** portal API extension A1 should consider, for example:

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
| Can iFilm share the 3CX token? | **No** — independent rotation/revocation/logging required |
| Locations API confirmed? | **Not yet** — `/agent/config` unread |
| Passwordless status API? | **No (LIVE 404)** |
| Safe for production iFilm enablement today? | **No** — missing iFilm token, live success schema, location payload, status enums |

---

## 11. Security rules for iFilm (unchanged)

- Browser → `ifilm.af` only
- iFilm backend → `https://portal.mns.af/api/voice-ai/v1` only
- Never store or log password, bearer token, or client secret
- Never send password to OpenAI or put it in stream tokens
- Never connect iFilm to SAS DBs
- Never reuse `MOBIN_PORTAL_AI_TOKEN`
- Logs may include: `client=ifilm`, branch, success/failure, stable customer id
