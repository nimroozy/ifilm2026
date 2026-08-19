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

**Desired** client distinction (verify / possibly extend portal middleware):

| `X-Mobin-Client` | Token |
|------------------|--------|
| `3cx-voice-agent` | existing 3CX secret (leave it on 3CX) |
| `ifilm` | **separate** iFilm secret |

PRIOR_3CX proves a bearer exists. It does **not** prove multi-client tokens already work. If only one global token is accepted, a small auth-middleware change is required. Independent rotation/revocation/logging remain required.

TLS required. Certificate validation enabled.

Unauthenticated LIVE response:

```json
{"success":false,"code":"unauthorized","message":"Invalid or missing service token."}
```

---

## 2. Service locations

`GET /api/voice-ai/v1/agent/config` is **voice-agent prompt/config** (`success`, `version`, `instructions`). It is **not** a location source.

No JSON locations route exists today (**LIVE** 404). Portal should add:

```http
GET /api/voice-ai/v1/service-locations
```

Preferred:

```json
{
  "success": true,
  "locations": [
    { "id": "1", "name": "Kabul", "active": true }
  ]
}
```

Use actual portal fields when implemented. Omit SAS hosts/secrets.

Known names (HTML + PRIOR_3CX) are bootstrap evidence only: Kabul, Kandahar, Ghazni, Nimruz, Buldak, Helmand.  
Do **not** hard-code them in iFilm as the long-term source. Cache the portal list on iFilm (~5 minutes).

---

## 3. Authenticate subscriber (existing — reuse)

```http
POST /api/voice-ai/v1/customers/lookup
```

### Request (PRIOR_3CX confirmed `request_source`)

```json
{
  "branch": "Kabul",
  "username": "customer123",
  "password": "customer-password",
  "request_source": "3cx_voice"
}
```

**Confirmed `request_source`:** `"3cx_voice"`.  
**iFilm value:** UNKNOWN — do **not** assume `"ifilm"` until portal accepts/documents it.

`branch` is a **name** in the 3CX integration (`Kabul`, …). Confirm whether numeric `branch_id` is also accepted; iFilm should send the canonical value from `/service-locations`.

### PRIOR_3CX success shape (nested — do not flatten)

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

Exact enums: **confirm with QA lookup**. Do not invent additional portal fields. Do not build DTOs from a flattened payload.

### PRIOR_3CX validation errors

HTTP 400/422 codes seen by 3CX: `invalid_branch`, `branch_rejected`, `username_rejected`, `password_rejected`.

iFilm customers must see a **generic** credential failure. Do not expose these codes in the UI.

### iFilm acceptance (after QA confirms enums)

Provisional:

```text
success == true
AND verified == true
AND internet service is usable
  (from customer.internet_status / customer.account_status / customer.expiry_date)
```

Then iFilm may issue its own subscriber JWT.  
Inactive/suspended/expired → deny playback; do not classify as “wrong password” if portal distinguishes them.

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

If `/customers/status` is deferred for v1, the exact policy is:

- Entitlement snapshot TTL = **15 minutes**
- After TTL expires, **new** protected playback is denied
- Customer must log in again
- Password is never stored
- Existing playback already issued is **not** retroactively recalled unless the current player/token architecture already supports that

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

- [ ] Dedicated iFilm credential issued (not the 3CX token); multi-client support verified or middleware extended
- [ ] `GET /service-locations` live (authoritative active locations; no SAS secrets)
- [ ] `POST /customers/lookup` succeeds for QA subscriber (nested `customer` object)
- [ ] Wrong password / branch / username → generic customer failure (`invalid_branch` etc. not shown)
- [ ] Suspended/expired QA → not treated as bad password
- [ ] Same username in two locations does not collide in iFilm
- [ ] `customer_number` uniqueness documented
- [ ] `account_status` / `internet_status` values documented from real payloads
- [ ] `request_source` value for iFilm confirmed (do not assume `ifilm`)
- [ ] Passwordless `/customers/status` **or** accepted TTL/re-login policy
- [ ] iFilm credential scoped away from `agent/config` / `packages/search` if possible
