# Portal Auth Audit — portal.mns.af × iFilm A1

**Date:** 2026-08-18  
**Baseline:** iFilm production `v1.17.0`  
**Portal:** `https://portal.mns.af` (Mobin Net Customer Portal — Laravel)  
**Portal source in Cursor workspace:** **NOT available**  
**Decision:** **STOP at contract boundary** — do not invent S2S endpoints; do not connect iFilm directly to SAS DBs.

---

## 1. Executive finding

`portal.mns.af` is a live **customer self-service web portal** (Laravel + cookie sessions + CSRF).

It already authenticates Internet subscribers with:

- Service Location (`branch_id`)
- Internet Username
- Password

That matches the **business UX** iFilm needs.

However, the **integration surface required for iFilm server-to-server auth is not present**.

What exists today is a **browser/session customer API**, not an authenticated partner/integration API.

Therefore A1 cannot be completed end-to-end until portal adds (or exposes) a dedicated iFilm integration contract.

---

## 2. Probe method

Performed against live `https://portal.mns.af` (read-only / invalid-credential probes only):

- HTTP discovery of common OpenAPI/Swagger/health/integration paths
- HTML inspection of `/login`
- JSON probes of `/api/customer/*`
- Invalid login POST to `/api/customer/login` with **nonexistent** username (no real customer password used)
- Artifact capture under `/opt/cursor/artifacts/a1-portal-audit/` and `docs/auth/screenshots/a1/`

No SAS DB credentials were used. No direct SAS connections were attempted.

---

## 3. Discovered portal surface (actual)

### 3.1 Customer login HTML (`GET /login`)

- App name: **Mobin Net Customer Portal**
- Session cookie: `mobin_net_ict_customer_portal_session` (HttpOnly)
- CSRF: `XSRF-TOKEN` + form `_token`
- Form `POST https://portal.mns.af/login` fields:
  - `branch_id` (required select)
  - `username` (label: Internet Username)
  - `password`
- Branches are **embedded in HTML options** (not loaded from a JSON locations API):

| branch_id | Display name |
|----------:|--------------|
| 1 | Kabul |
| 2 | Nimruz |
| 3 | Kandahar |
| 4 | Ghazni |
| 5 | Helmand |
| 6 | Buldak |

Evidence: `docs/auth/branches-from-login-html.json`, screenshots in `docs/auth/screenshots/a1/`.

### 3.2 Customer JSON API (partial)

| Method | Path | Observed |
|--------|------|----------|
| `POST` | `/api/customer/login` | **Exists.** Requires `branch_id`, `username`, `password`. Empty body → `422` validation. Fake user → `401` `{"message":"Invalid username or password."}` |
| `GET` | `/api/customer/service` | **Exists.** Unauthenticated → `401` `{"message":"Unauthenticated."}` |
| `GET` | `/api/customer/invoices` | **Exists.** Unauthenticated → `401` |
| `GET` | `/up` | Laravel up check (HTML) |

### 3.3 Explicitly missing (404)

Preferred / equivalent integration endpoints **not found**:

- `GET /api/integrations/ifilm/service-locations`
- `POST /api/integrations/ifilm/authenticate`
- `POST /api/integrations/ifilm/validate`
- Any `/api/integrations/*`, `/api/partner/*`, `/api/ifilm/*`, `/api/external/*`
- Public JSON branches/locations endpoint
- OpenAPI / Swagger docs
- OAuth/token endpoint for service clients
- Passwordless entitlement validate endpoint

### 3.4 Authentication mechanism between iFilm and portal

**Not discovered.**

Observed portal auth is:

1. Browser fetches `/login` → receives CSRF + session cookies
2. Browser/API client posts credentials with CSRF headers
3. Response for failure is generic JSON message
4. Success schema is **unknown** (no QA subscriber credentials used in this audit)

This is a **session/CSRF browser model**, not a documented service-credential S2S model.

No evidence of:

- `PORTAL_IFILM_CLIENT_ID` / client secret support
- HMAC signed requests
- mTLS partner auth
- scoped integration tokens

### 3.5 Service-location identifier

Actual field name on portal login: **`branch_id`** (integer).

Observed IDs: `1..6` with display names above.

No JSON schema for `code`, `active`, `sort_order` was found via API.

### 3.6 Subscriber identifier / status fields

**Unknown from public probes.**

`/api/customer/service` exists but requires authentication; success payload not observed.

No public documentation of:

- stable portal subscriber id
- package name
- expiry
- account/service status enums
- `ifilm_allowed` entitlement flag

### 3.7 Timeout / error behavior (observed)

| Case | HTTP | Body |
|------|-----:|------|
| Missing fields | 422 | Laravel validation errors naming `branch_id`, `username`, `password` |
| Invalid credentials | 401 | `{"message":"Invalid username or password."}` |
| Unauthenticated resource | 401 | `{"message":"Unauthenticated."}` |
| Missing route | 404 | Laravel JSON route-not-found |

Connect/read latency was normal for public HTTPS; no special timeout contract documented.

### 3.8 Can portal issue an auth/session assertion for iFilm?

**Not evidenced.**

Current `/api/customer/login` appears oriented to establishing a **portal customer session**, not returning a signed short-lived assertion for a third party (iFilm).

---

## 4. Why existing `/api/customer/login` is not sufficient for A1

Even though it validates `branch_id + username + password`, it is unsuitable as the production iFilm integration without portal changes:

1. **CSRF/session coupling** — designed for browser cookie auth, not headless S2S.
2. **No service credential / scoped partner auth** discovered.
3. **No locations API** — scraping HTML for branches is brittle and forbidden by A1 (“portal response is authoritative” via API).
4. **Success/entitlement schema unknown** — cannot assert `service.active` + `ifilm_allowed` safely.
5. **No passwordless revalidation** endpoint for entitlement TTL refresh.
6. Using it as-is would risk treating HTTP 200/session as entitlement (explicitly disallowed).

**Do not hardcode the HTML branch list into iFilm as a permanent locations source.**

---

## 5. iFilm current auth attach points (relevant)

iFilm already has a pluggable subscriber identity layer:

- `SubscriberIdentityProvider` (`fixture` / `radius` / `demo` / `disabled`)
- Local `subscribers` table with `identity_provider` + `external_subject`
- JWT `typ=subscriber` + refresh tokens
- Entitlement snapshots gating playback session create
- Login rate limit on subscriber login

Production default: identity mode **disabled**; live Radius **unverified** and **not** the A1 path.

A1 must add a **portal HTTP provider**, not wire iFilm to SAS DBs and not treat UDP Radius as the portal replacement.

---

## 6. Required portal API (contract gap)

Until portal implements an iFilm integration API, A1 implementation must stop here.

See:

- `docs/auth/PORTAL_IFILM_INTEGRATION_CONTRACT.md` — exact required endpoints/schemas
- `docs/auth/PORTAL_AUTH_ARCHITECTURE.md` — target iFilm design once contract exists

Minimum portal deliverables for A1 to resume:

1. Service-authenticated locations JSON API
2. Service-authenticated authenticate API returning stable subject + service/entitlement
3. Passwordless validate API (or signed short-lived assertion) for entitlement recheck
4. Partner credential restricted to those scopes only

---

## 7. Security notes from audit

- Invalid login message is already generic (good against enumeration)
- Portal copy states password is not stored on portal servers (claimed; not independently verified here)
- iFilm must still never store portal/SAS passwords
- iFilm browser must never call portal directly (CORS/secrets)
- No portal client secret exists in iFilm today (confirmed by codebase search)

---

## 8. Conclusion

| Question | Answer |
|----------|--------|
| Does portal already do location + username + password login for customers? | **Yes** (HTML + `/api/customer/login`) |
| Does portal expose an iFilm S2S integration contract? | **No** |
| Can A1 ship production portal auth now? | **No — blocked on portal contract** |
| May iFilm bypass portal and talk to SAS DBs? | **No** |
| Next step | Portal team implements integration contract; then iFilm implements A1 client + login UI |

**Status: CONTRACT AUDIT COMPLETE — IMPLEMENTATION STOPPED AT BOUNDARY**
