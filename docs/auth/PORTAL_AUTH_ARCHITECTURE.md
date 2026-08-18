# A1 Portal Auth Architecture (Target)

**Status:** Target design — blocked on portal integration contract  
**Baseline:** iFilm `v1.17.0`  
**See also:** `PORTAL_AUTH_AUDIT.md`, `PORTAL_IFILM_INTEGRATION_CONTRACT.md`

---

## 1. Trust boundary

```text
Customer Browser
      |
      | HTTPS (no portal secrets)
      v
   ifilm.af  (API + UI)
      |
      | HTTPS server-to-server + partner credential
      v
 portal.mns.af
      |
      | internal mapping (not visible to iFilm)
      v
 Service Location / SAS
      |
      v
 Subscriber account
```

Forbidden:

```text
ifilm.af → Kabul SAS DB
ifilm.af → Kandahar SAS DB
...
```

---

## 2. iFilm responsibilities

1. Render Sign In with Service Location + Internet Username + Password.
2. `GET /api/auth/isp/locations` → portal locations (cached ~5 min).
3. `POST /api/auth/isp/login` → portal authenticate (S2S).
4. On success: create/link local subscriber + external identity; issue normal iFilm JWT/refresh.
5. Revalidate entitlement via portal validate/assertion within TTL before new protected playback sessions.
6. Keep admin auth separate and unchanged.

---

## 3. Local identity model

Reuse existing `subscribers` as the local customer user.

Add (when implementing) `external_subscriber_identities` (or equivalent):

| Column | Purpose |
|--------|---------|
| `user_id` / `subscriber_id` | FK to local subscriber |
| `provider` | `portal_mns` |
| `external_subject` | portal stable subscriber id (preferred) |
| `service_location_id` | portal location id |
| `service_location_code` | optional |
| `subscriber_username` | last verified username (display/audit) |
| `last_verified_at` | last successful portal auth/validate |
| `entitlement_valid_until` | cache expiry |
| timestamps | created/updated |

Uniques:

- `(provider, external_subject)` when stable id exists
- else `(provider, service_location_id, subscriber_username)`

**Never store passwords.**

JWT `sub` remains local subscriber integer id so Watchlist / CW / progress / recommendations keep working.

---

## 4. Session model

After portal success:

- Issue existing subscriber access JWT + refresh token family
- Register device session as today
- Snapshot entitlement into existing entitlement snapshot tables

Subsequent API calls do **not** hit portal each time.

Playback session create rechecks entitlement; if snapshot older than TTL, call portal validate (no password).

---

## 5. Failure policy

| Situation | Behavior |
|-----------|----------|
| Portal down on login | Deny login |
| Portal down on validate | Do not extend entitlement; deny new protected playback when cache expired |
| Invalid credentials | Generic error |
| Inactive service | Inactive service message |
| Admin login | Unaffected |

Fail closed. Never fail open indefinitely.

---

## 6. Configuration (target)

Backend-only:

```text
PORTAL_AUTH_ENABLED=false          # flip true after portal contract live
PORTAL_BASE_URL=https://portal.mns.af
PORTAL_IFILM_CLIENT_ID=ifilm
PORTAL_IFILM_CLIENT_SECRET=...
PORTAL_LOCATION_CACHE_TTL_SECONDS=300
PORTAL_CONNECT_TIMEOUT_SECONDS=3
PORTAL_READ_TIMEOUT_SECONDS=5
PORTAL_ENTITLEMENT_CACHE_TTL_SECONDS=900
ALLOW_LOCAL_CUSTOMER_LOGIN=false
SUBSCRIBER_IDENTITY_MODE=portal    # new mode once implemented
```

No `VITE_*` secrets.

---

## 7. Frontend (target)

Login-only UI change on `/login`:

- Service Location select (from `/api/auth/isp/locations`)
- Internet Username
- Password
- EN/FA/PS RTL strings
- Loading / retry / generic errors
- No browser calls to portal.mns.af

Do not redesign homepage, Movie Detail, Series Detail, or player.

---

## 8. Migration plan (when implementing)

Expected Alembic head today: `023_media_tracks_packaging_v1`  
Next: `024_external_subscriber_identities` (name TBD)

One head only. No historical migration edits.

---

## 9. Rollback

Feature flag off (`PORTAL_AUTH_ENABLED=false`) returns customer login to previous policy (disabled/local/demo as configured).  
Admin auth unchanged.  
Release rollback to `v1.17.0` remains valid until A1 ships.

---

## 10. Current stop reason

Portal integration endpoints are missing. Architecture is ready; implementation waits for contract delivery documented in `PORTAL_IFILM_INTEGRATION_CONTRACT.md`.
