# Portal ↔ iFilm integration contract (reuse `/api/voice-ai/v1`)

**Status:** Reuse existing 3CX partner API; do **not** add `/api/integrations/ifilm/*`  
**Consumer:** `ifilm.af` backend only  
**Provider:** `https://portal.mns.af/api/voice-ai/v1`  
**Auth model:** Bearer service token + `X-Mobin-Client`

Live evidence: `docs/auth/VOICE_AI_V1_LIVE_CONTRACT.md`

This file replaces the earlier “invent `/api/integrations/ifilm/*`” draft. Semantics (portal brokers SAS; no password storage; fail closed) are unchanged. **Paths follow the existing voice-ai API.**

---

## 0. Non-negotiables

1. iFilm never connects to SAS DBs.
2. Portal owns location → SAS mapping.
3. Passwords are transient request fields only (never stored by iFilm).
4. Browser talks only to `ifilm.af`.
5. iFilm uses its **own** portal credential — not `MOBIN_PORTAL_AI_TOKEN`.
6. HTTP 200 alone is not entitlement — map `verified` + service fields from the **real** lookup payload.

---

## 1. Partner authentication

```http
Authorization: Bearer <IFILM_PORTAL_TOKEN>
X-Mobin-Client: ifilm
Accept: application/json
Content-Type: application/json
```

Portal should distinguish clients:

| `X-Mobin-Client` | Token |
|------------------|--------|
| `3cx-voice-agent` | existing 3CX secret (leave it on 3CX) |
| `ifilm` | **new** iFilm secret |

Independent rotation, revocation, logging, and (if supported) rate limits.

TLS required. Certificate validation enabled.

Unauthenticated LIVE response:

```json
{"success":false,"code":"unauthorized","message":"Invalid or missing service token."}
```

---

## 2. Service locations

### Inspect first (existing)

```http
GET /api/voice-ai/v1/agent/config
```

If this already returns customer-facing branches / provinces / location names, **reuse that list**. Cache on iFilm (~5 minutes). Never persist SAS hosts.

### Only if `/agent/config` has no locations

Small additive endpoint on the **same** API (portal change):

```http
GET /api/voice-ai/v1/service-locations
```

Preferred items: `id` or stable name, `name`, `active`. Omit SAS secrets.

Do **not** hard-code Kabul/Nimruz/… in iFilm as the long-term source.  
HTML `/login` options are bootstrap evidence only.

---

## 3. Authenticate subscriber (existing — reuse)

```http
POST /api/voice-ai/v1/customers/lookup
```

### Request (operator shape)

```json
{
  "branch": "Kabul",
  "username": "customer123",
  "password": "customer-password",
  "request_source": "ifilm"
}
```

`request_source` must be whatever portal already allows. Confirm after the iFilm token exists. Do not invent an enum if portal validates a list (`3cx_voice` is the known 3CX value).

`branch` is a **name** in the 3CX integration (`Kabul`, …). Confirm whether numeric `branch_id` is also accepted; iFilm should send the canonical value portal returns from config.

### Success fields (operator names — live values not yet captured)

```json
{
  "success": true,
  "verified": true,
  "display_name": "...",
  "customer_number": "...",
  "branch": "Kabul",
  "account_status": "...",
  "internet_status": "...",
  "current_package": "...",
  "expiry_date": "...",
  "days_remaining": 0
}
```

Exact enums and extra fields: **confirm with QA lookup**. iFilm must not invent additional portal fields.

### iFilm acceptance (after QA confirms enums)

Provisional:

```text
verified == true
AND internet service is usable
  (from actual internet_status / account_status / expiry_date)
```

Then iFilm may issue its own subscriber JWT.  
Inactive/suspended/expired → deny playback; do not classify as “wrong password” if portal distinguishes them.

Invalid location / username / password → generic customer error.

---

## 4. Stable subscriber id

Audit `customer_number` on a real payload:

| If | Then `external_subject` |
|----|-------------------------|
| Globally unique across SAS branches | `customer_number` |
| Location-scoped only | `{canonical_branch}:{customer_number}` |

`provider = portal_mns`  
Never username alone.

---

## 5. Passwordless revalidation (gap)

**No existing `/voice-ai/v1` endpoint does this** (live 404).

Do not persist the Internet password.

Preferred small portal addition (same API family):

```http
POST /api/voice-ai/v1/customers/status
```

```json
{
  "branch": "Kabul",
  "customer_number": "<stable id>"
}
```

Portal re-queries **current** SAS/service state. No password.

Until then, iFilm uses a bounded entitlement cache TTL and **fails closed** on new protected playback when the cache expires (customer signs in again).

Do **not** rebuild authenticate/locations just because validate is missing.

---

## 6. Timeouts (iFilm client)

- connect ≤ 3s
- read ≤ 5s  
Fail closed on login timeout.

---

## 7. Logging

Allowed: `client=ifilm`, branch, outcome, latency, stable customer id.

Forbidden: password, bearer token, client secret, SAS credentials.

---

## 8. Rate limits

LIVE unauthenticated: Laravel `X-RateLimit-Limit: 60`.  
Authenticated / per-username policy: unknown — confirm on portal.

iFilm should still apply its own subscriber-login rate limit.

---

## 9. Acceptance checklist (portal + QA)

- [ ] Dedicated `X-Mobin-Client: ifilm` token issued (not the 3CX token)
- [ ] `GET /agent/config` inspected; locations source decided
- [ ] Additive `/service-locations` only if config has no locations
- [ ] `POST /customers/lookup` succeeds for QA subscriber in location A
- [ ] Wrong password → generic failure
- [ ] Wrong location → generic / denied (no enumeration)
- [ ] Suspended/expired QA → not treated as bad password
- [ ] Same username in two locations does not collide in iFilm
- [ ] `customer_number` uniqueness documented
- [ ] `account_status` / `internet_status` enums documented from real payloads
- [ ] `request_source` value for iFilm confirmed
- [ ] Passwordless `/customers/status` **or** accepted TTL/fail-closed policy
- [ ] No SAS secrets in responses
- [ ] iFilm token scoped away from unnecessary voice-agent package tools if possible
