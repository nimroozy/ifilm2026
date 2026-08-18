# Portal Auth Audit — portal.mns.af × iFilm A1

**Date:** 2026-08-18 (corrected)  
**Baseline:** iFilm production `v1.17.0`  
**Portal:** `https://portal.mns.af` (Mobin Net ICT Customer Portal — Laravel)  
**Portal source in Cursor workspace:** **NOT available**  
**Correction:** The first pass searched `/api/integrations/ifilm/*` and wrongly concluded portal had no S2S API.

**Authoritative live contract:** `docs/auth/VOICE_AI_V1_LIVE_CONTRACT.md`

---

## 1. Executive finding (corrected)

`portal.mns.af` already has **two** customer-auth surfaces:

1. **Browser / CSRF session** — HTML `/login` + `POST /api/customer/login`  
2. **Server-to-server partner API** — `https://portal.mns.af/api/voice-ai/v1`  
   originally built for the **3CX voice agent**

A1 must **reuse** `/api/voice-ai/v1`, not invent `/api/integrations/ifilm/*`.

iFilm still **must not** talk to SAS DBs. Portal remains the broker.

A1 implementation is **not** blocked on “missing S2S API.”  
It **is** blocked on:

1. A **dedicated iFilm** service token (do not reuse the 3CX token)
2. Live success QA of `POST /customers/lookup` with a dedicated QA subscriber
3. Confirming whether `GET /agent/config` returns service locations
4. A passwordless current-status method (missing today) **or** an explicit TTL/fail-closed policy

---

## 2. Probe method (this correction)

Against live `https://portal.mns.af`:

- Re-probed `/api/voice-ai/v1/*` existence via GET/POST/OPTIONS/405/404
- Invalid/missing bearer only — **no real 3CX token used or logged**
- Fake `X-Mobin-Client: ifilm` and `3cx-voice-agent` (token still rejected)
- CORS preflight from `https://ifilm.af` and an arbitrary origin
- Reconfirmed HTML `/login` branches (unchanged)
- No SAS DB connections
- No customer passwords (dummy body fields only, never logged as secrets)

---

## 3. Existing S2S API (LIVE)

### 3.1 Partner auth

```http
Authorization: Bearer <service token>
X-Mobin-Client: <client id>
Accept: application/json
```

Missing/invalid token → `401`

```json
{"success":false,"code":"unauthorized","message":"Invalid or missing service token."}
```

`X-Mobin-Client` is CORS-allowed and is the existing client-identity header.  
`X-Client-Id` is **not** the portal convention.

iFilm desired identity: `X-Mobin-Client: ifilm` + its **own** bearer.  
Portal must issue that credential. This workspace has **no** iFilm portal token and must not be given the 3CX token.

### 3.2 Endpoints

| Method | Path | Role for A1 |
|--------|------|-------------|
| `GET` | `/api/voice-ai/v1/agent/config` | **First** location/config source to inspect with an iFilm token |
| `POST` | `/api/voice-ai/v1/customers/lookup` | **Reuse** for branch + username + password verify |
| `POST` | `/api/voice-ai/v1/packages/search` | Exists; **not required** for A1 |

### 3.3 Not present (do not rebuild the whole auth API)

| Path | Result |
|------|--------|
| `/api/voice-ai/v1/service-locations` | 404 |
| `/api/voice-ai/v1/customers/validate` | 404 |
| `/api/voice-ai/v1/customers/status` | 404 |
| `/api/integrations/ifilm/*` | 404 (irrelevant now) |

---

## 4. Browser customer portal (unchanged, still useful)

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/login` | Service Location + Internet Username + Password |
| `POST` | `/api/customer/login` | CSRF/session; `branch_id` + username + password |
| `GET` | `/api/customer/service` | Session required |
| `GET` | `/api/customer/invoices` | Session required |
| `GET` | `/up` | Laravel up (title: Mobin Net ICT Customer Portal) |

HTML branches (not a JSON API):

| branch_id | Name |
|----------:|------|
| 1 | Kabul |
| 2 | Nimruz |
| 3 | Kandahar |
| 4 | Ghazni |
| 5 | Helmand |
| 6 | Buldak |

Operator-normalized voice-ai `branch` strings use the **same names**.  
Do not hard-code this list in iFilm as the long-term source.

---

## 5. What we could not observe without an iFilm token

- Exact `/customers/lookup` success JSON (operator field **names** only)
- Exact `account_status` / `internet_status` enums
- How expired vs suspended is represented
- Whether `customer_number` is globally unique
- Whether username collides across branches
- Whether `branch` accepts IDs (`1`) as well as `"Kabul"`
- Allowed `request_source` values
- `/agent/config` body (branches or not)
- Authenticated rate-limit policy / token scopes
- Successful QA lookup

**Successful QA lookup: NOT RUN** — no dedicated iFilm token and no QA subscriber secret in this environment. Do not use the 3CX token to force a success payload.

---

## 6. iFilm attach points (unchanged)

- `SubscriberIdentityProvider` (`fixture` / `radius` / `demo` / `disabled`)
- Local `subscribers` (`identity_provider` + `external_subject`)
- JWT `typ=subscriber` + entitlement snapshots
- Current `/login` UI: username + password only (no location dropdown yet)
- `authenticate(username, password)` has **no branch argument** today
- `upsert_subscriber_from_identity` can collide on username across locations

Production default: identity mode **disabled**. Live Radius is **not** the A1 path.

---

## 7. Security notes

- Unauthorized voice-ai errors do not echo the token (good)
- `Cache-Control: no-store` on unauthorized JSON
- Unauthenticated throttle header: `X-RateLimit-Limit: 60`
- CORS `Access-Control-Allow-Origin: *` — keep iFilm token server-side
- Portal `/api/customer/login` invalid message remains generic
- iFilm still must never store Internet passwords

---

## 8. Conclusion

| Question | Answer |
|----------|--------|
| Does portal already have an S2S customer API? | **Yes** — `/api/voice-ai/v1` |
| Should A1 create `/api/integrations/ifilm/*`? | **No** |
| Should iFilm reuse `/customers/lookup`? | **Yes, after iFilm token + QA** |
| May iFilm reuse the 3CX bearer? | **No** |
| Locations JSON confirmed? | **Not yet** — inspect `/agent/config` first |
| Passwordless validate exists? | **No** |
| Can A1 enable production portal login now? | **No** |
| May iFilm talk to SAS DBs? | **No** |

**Status: CORRECTED AUDIT COMPLETE — IMPLEMENTATION WAITING ON IFILM TOKEN + QA LOOKUP**
