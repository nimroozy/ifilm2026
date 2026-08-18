# A1 Portal Auth Architecture (Target)

**Status:** Target design — reuse `/api/voice-ai/v1`; waiting on iFilm token + QA lookup  
**Baseline:** iFilm `v1.17.0`  
**See also:** `PORTAL_AUTH_AUDIT.md`, `VOICE_AI_V1_LIVE_CONTRACT.md`

---

## 1. Trust boundary

```text
Customer Browser
      |
      | HTTPS (no portal secrets)
      v
   ifilm.af  (API + UI)
      |
      | HTTPS S2S
      | Authorization: Bearer <IFILM_PORTAL_TOKEN>
      | X-Mobin-Client: ifilm
      v
 portal.mns.af /api/voice-ai/v1
      |
      | internal mapping (not visible to iFilm)
      v
 Service Location / SAS
```

Forbidden: `ifilm.af → SAS DB`.  
Forbidden: iFilm configured with `MOBIN_PORTAL_AI_TOKEN`.

---

## 2. iFilm responsibilities

1. Render Sign In: Service Location + Internet Username + Password (EN/FA/PS).
2. `GET /api/auth/isp/locations` → portal `GET /api/voice-ai/v1/service-locations` (not `/agent/config`), cached ~5 min.
3. `POST /api/auth/isp/login` (or extend existing subscriber login with `branch`) → S2S `POST /customers/lookup`.
4. On success: link local subscriber via `portal_mns` + stable `external_subject`; issue existing iFilm JWT/refresh.
5. Snapshot entitlement from mapped portal fields. Recheck before new playback if snapshot older than TTL.
6. Passwordless portal status **if/when** portal adds it; otherwise fail closed after TTL.
7. Keep admin auth separate and unchanged.

---

## 3. Local identity model

Reuse `subscribers`.

Prefer existing columns first:

- `identity_provider = portal_mns`
- `external_subject` = `customer_number` or `branch:customer_number`
- `branch` / `package` / `status` / `service_status` / `valid_until` already exist

Add Alembic `024_external_subscriber_identities` **only if** we need extra fields (last username, location code, last_verified_at) that do not fit safely on `subscribers`.

Uniques: `(identity_provider, external_subject)`.

**Never store passwords.**

JWT `sub` remains local subscriber integer id (Watchlist / CW / progress keep working).

Implementation must stop matching solely on `username` when upserting portal users (collision across locations).

`SubscriberIdentityProvider.authenticate` today is `(username, password)`. Portal mode needs **branch** (extend the protocol or add a portal-specific login path). Do not drop branch.

---

## 4. Session model

After lookup success + usable internet service:

- Issue existing subscriber access JWT + refresh family
- Register device session as today
- Write entitlement snapshot

Subsequent API calls do **not** hit portal each time.

Playback session create: if snapshot older than TTL, call portal status (no password) **or** deny if that API does not exist yet.

---

## 5. Failure policy

| Situation | Behavior |
|-----------|----------|
| Portal down on login | Deny login |
| Portal down / no passwordless status | Do not extend entitlement; deny new protected playback when cache expired |
| Invalid credentials | Generic error |
| Inactive / expired / suspended | Inactive-service message (once portal distinguishes) |
| Admin login | Unaffected |

Fail closed.

---

## 6. Configuration (target)

Backend-only. Default **off**.

```text
PORTAL_AUTH_ENABLED=false
PORTAL_BASE_URL=https://portal.mns.af
PORTAL_VOICE_AI_PREFIX=/api/voice-ai/v1
PORTAL_IFILM_CLIENT=ifilm
PORTAL_IFILM_TOKEN=...          # IFILM_PORTAL_TOKEN — never MOBIN_PORTAL_AI_TOKEN
PORTAL_REQUEST_SOURCE=          # do not default to ifilm; set only after portal accepts it
PORTAL_LOCATION_CACHE_TTL_SECONDS=300
PORTAL_CONNECT_TIMEOUT_SECONDS=3
PORTAL_READ_TIMEOUT_SECONDS=5
PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS=900
SUBSCRIBER_IDENTITY_MODE=portal
ALLOW_LOCAL_CUSTOMER_LOGIN=false
```

No `VITE_*` portal secrets.  
Do not add env aliases that read the 3CX token name.

---

## 7. Frontend (target)

Login-only change on `/login`:

- Service Location select (from `/api/auth/isp/locations`)
- Internet Username
- Password
- EN/FA/PS RTL
- Loading / retry / generic errors
- No browser calls to `portal.mns.af`

Do not redesign homepage, Movie Detail, Series Detail, or player.

---

## 8. Migration plan

Current Alembic head: `023_media_tracks_packaging_v1`  
Next, **only if needed:** `024_…` one new head.

---

## 9. Rollback

`PORTAL_AUTH_ENABLED=false` / identity mode not `portal` → previous subscriber policy.  
Admin auth unchanged.  
Release rollback to `v1.17.0` remains valid until A1 ships.

---

## 10. Current stop reason

S2S API **exists**. `/agent/config` is voice-agent prompt/config, not locations. Implementation waits on: dedicated iFilm credential (verify/extend multi-token middleware), `GET /service-locations`, one QA lookup (nested `customer` shape), confirmed identity/status/`request_source`, and passwordless `/customers/status` **or** explicit TTL/re-login.
