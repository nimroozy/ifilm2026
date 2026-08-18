# Portal ↔ iFilm Integration Contract (Required)

**Status:** REQUIRED before A1 implementation can proceed  
**Consumer:** `ifilm.af` backend only (server-to-server)  
**Provider:** `portal.mns.af`  
**Auth model:** partner/service credential (not browser CSRF session)

This contract is the preferred clean API when no equivalent already exists.  
Live audit (2026-08-18) found **no** `/api/integrations/ifilm/*` routes.

Names may change if portal already has equivalents — iFilm will adapt to real paths once published. Semantics must remain.

---

## 0. Non-negotiables

1. iFilm never connects to SAS DBs.
2. Portal owns location → SAS mapping.
3. Passwords are transient request fields only (never stored by iFilm).
4. Browser talks only to `ifilm.af`.
5. Partner credential is scoped; no portal admin access.
6. HTTP 200 alone is not entitlement — explicit active + ifilm_allowed required.

---

## 1. Partner authentication

Every integration request must authenticate the iFilm service.

### Preferred: HTTP Bearer service token

```http
Authorization: Bearer <PORTAL_IFILM_CLIENT_SECRET>
X-Client-Id: ifilm
```

Or OAuth2 client-credentials if portal already has it.

Scopes (minimum):

- `ifilm.locations.read`
- `ifilm.subscriber.authenticate`
- `ifilm.subscriber.validate`

TLS required. Certificate validation enabled.

---

## 2. Service locations

### `GET /api/integrations/ifilm/service-locations`

Returns only **active customer-facing** locations.

### Response 200

```json
{
  "locations": [
    {
      "id": "1",
      "code": "KBL",
      "name": "Kabul",
      "active": true,
      "sort_order": 1
    },
    {
      "id": "3",
      "code": "KDR",
      "name": "Kandahar",
      "active": true,
      "sort_order": 2
    }
  ]
}
```

### Field rules

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Opaque portal location id (string or int serialized as string). Today HTML uses numeric `branch_id`. |
| `code` | recommended | Short display/code; optional if portal has none |
| `name` | yes | Customer-facing name |
| `active` | yes | Inactive must be omitted or `active=false` filtered by portal |
| `sort_order` | optional | Ascending |

### Must NOT include

- SAS DB host / credentials
- Radius secrets
- Internal server IPs
- Unnecessary internal DB identifiers

### Errors

| HTTP | Meaning |
|-----:|---------|
| 401/403 | Partner auth failed |
| 5xx | Portal unavailable |

---

## 3. Authenticate subscriber

### `POST /api/integrations/ifilm/authenticate`

### Request

```json
{
  "location_id": "1",
  "username": "customer123",
  "password": "customer-password"
}
```

Portal performs:

```text
location_id → SAS mapping → subscriber lookup → password check → service status
```

### Success 200

```json
{
  "authenticated": true,
  "subscriber": {
    "id": "stable-portal-subscriber-id",
    "username": "customer123",
    "location_id": "1",
    "location_code": "KBL",
    "location_name": "Kabul"
  },
  "service": {
    "active": true,
    "status": "active",
    "expires_at": null,
    "package_name": "Premium 50Mbps"
  },
  "entitlement": {
    "ifilm_allowed": true
  },
  "assertion": {
    "token": "opaque-or-signed-short-lived-token",
    "expires_at": "2026-08-18T12:00:00Z"
  }
}
```

### Acceptance rule for iFilm sign-in

```text
authenticated == true
AND service.active == true
AND entitlement.ifilm_allowed == true
```

All three required.

### Stable subscriber id

`subscriber.id` **must** be globally stable across locations when it is the same person.

If portal cannot provide a stable id, document that explicitly. iFilm fallback key becomes:

```text
portal_mns:{location_id}:{normalized_username}
```

Same username in Kabul vs Kandahar must not collide unless portal asserts same `subscriber.id`.

### Failure responses (recommended)

| HTTP | `code` | Customer mapping |
|-----:|--------|------------------|
| 401 | `invalid_credentials` | Generic invalid location/username/password |
| 403 | `service_inactive` | Internet service inactive |
| 403 | `ifilm_not_allowed` | Service inactive / not entitled (same customer message unless product wants distinct) |
| 404 | `location_unknown` | Generic invalid credentials (avoid enumeration) |
| 429 | `rate_limited` | Try again later |
| 503 | `upstream_unavailable` | Auth temporarily unavailable |

Do not return different messages for “user exists / wrong password”.

### Assertion (strongly preferred)

`assertion.token` enables passwordless revalidation.

If portal cannot issue assertion/token in v1, document limitation; iFilm will use a bounded local entitlement TTL and deny new protected playback after expiry until re-login.

---

## 4. Validate entitlement (passwordless)

### `POST /api/integrations/ifilm/validate`

### Request

```json
{
  "subscriber_id": "stable-portal-subscriber-id",
  "location_id": "1",
  "assertion_token": "opaque-or-signed-short-lived-token"
}
```

### Success 200

```json
{
  "valid": true,
  "subscriber": {
    "id": "stable-portal-subscriber-id",
    "location_id": "1"
  },
  "service": {
    "active": true,
    "status": "active",
    "expires_at": null,
    "package_name": "Premium 50Mbps"
  },
  "entitlement": {
    "ifilm_allowed": true
  },
  "assertion": {
    "token": "rotated-or-same-token",
    "expires_at": "2026-08-18T12:15:00Z"
  }
}
```

### Failure

| HTTP | `code` |
|-----:|--------|
| 401 | `assertion_invalid` / `assertion_expired` |
| 403 | `service_inactive` / `ifilm_not_allowed` |
| 503 | `upstream_unavailable` |

**Never requires password.**

---

## 5. Timeouts

Suggested portal SLO for iFilm client configuration:

- connect ≤ 3s
- read ≤ 5s

On timeout, iFilm fails closed for new login.

---

## 6. Logging (portal side)

Allowed: partner id, location id, outcome, latency, stable subscriber id.

Forbidden: password, password hashes, SAS secrets, raw Radius packets with secrets.

---

## 7. Compatibility note vs today’s `/api/customer/login`

Today’s browser endpoint proves portal can validate `branch_id + username + password`.

It is **not** this contract:

- CSRF/session oriented
- no partner auth
- no locations JSON API
- success/entitlement schema undocumented here
- no validate-without-password

Portal may implement the integration routes as a thin wrapper over the same internal auth service used by `/api/customer/login`, without exposing SAS details.

---

## 8. Acceptance checklist for portal delivery

- [ ] Partner credential works from iFilm backend IP/network path
- [ ] Locations endpoint returns active branches only
- [ ] Authenticate succeeds for QA subscriber in location A
- [ ] Authenticate fails for wrong password (generic)
- [ ] Authenticate fails/inactive for suspended QA account
- [ ] Same username in two locations maps correctly (stable id or non-colliding subjects)
- [ ] Validate works without password using assertion
- [ ] No SAS secrets in responses
- [ ] Rate limiting on authenticate
