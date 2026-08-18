# A1 — Portal/SAS Subscriber Authentication Report

**Status:** CORRECTED AUDIT — reuse `/api/voice-ai/v1`; implementation not started  
**Train:** A1 (prioritized ahead of G3 / T1 / player)  
**Baseline:** production `v1.17.0`  
**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** *(updated after push)*

**Do not merge as an auth implementation. Do not deploy. Do not start G3/T1/player redesign.**

---

## Verdict (corrected)

The first A1 pass searched the **wrong namespace** (`/api/integrations/ifilm/*`) and concluded portal had no server-to-server API.

**That conclusion is wrong.**

Portal already has a partner JSON API:

```text
https://portal.mns.af/api/voice-ai/v1
```

Originally built for the **3CX voice agent**.

A1 must **reuse** this API. Do **not** create duplicate `/api/integrations/ifilm/*` authenticate endpoints.

iFilm still **must not** talk to SAS DBs.

A1 code (portal client, location dropdown, identity, entitlement mapping) waits on:

1. A **dedicated iFilm** portal token (`X-Mobin-Client: ifilm`) — **not** `MOBIN_PORTAL_AI_TOKEN`
2. A successful QA `POST /customers/lookup` (real schema + status enums)
3. Reading `GET /agent/config` for locations
4. Passwordless status (missing) **or** an accepted TTL/fail-closed policy

---

## 1. Exact `/voice-ai/v1` contract

See `docs/auth/VOICE_AI_V1_LIVE_CONTRACT.md`.

| Method | Path | LIVE |
|--------|------|------|
| `GET` | `/api/voice-ai/v1/agent/config` | Exists; 401 without token |
| `POST` | `/api/voice-ai/v1/customers/lookup` | Exists; POST-only; 401 without token |
| `POST` | `/api/voice-ai/v1/packages/search` | Exists; not needed for A1 |

Partner auth (LIVE + operator):

```http
Authorization: Bearer <service token>
X-Mobin-Client: 3cx-voice-agent | ifilm
Accept: application/json
```

Missing/invalid token:

```json
{"success":false,"code":"unauthorized","message":"Invalid or missing service token."}
```

CORS: `Access-Control-Allow-Origin: *` and allows `authorization`, `x-mobin-client`. Keep the token on the iFilm backend only.

Rate limit (LIVE unauthenticated): `X-RateLimit-Limit: 60`. Authenticated policy unknown.

---

## 2. Successful QA lookup

**Not run.**

This environment has no dedicated iFilm portal token and must not use the 3CX bearer. No QA subscriber secret is available here.

Operator-reported success **field names** (values/enums unverified):

`success`, `verified`, `display_name`, `customer_number`, `branch`, `account_status`, `internet_status`, `current_package`, `expiry_date`, `days_remaining`

---

## 3. Location source

| Source | Status |
|--------|--------|
| `GET /api/voice-ai/v1/agent/config` | **First to reuse** — body unread (token required) |
| Dedicated `/voice-ai/v1/service-locations` | **404** |
| HTML `/login` options | Same six names; **not** the long-term API |
| Hard-coded iFilm list | **Forbidden** as the long-term solution |

If `/agent/config` has no locations, portal should add **only** `GET /api/voice-ai/v1/service-locations`.

---

## 4. Stable identity field

**Candidate:** `customer_number` (`provider=portal_mns`).

**Uniqueness:** UNKNOWN until QA compares two branches (and a duplicate username if available).

If not globally unique: `external_subject = {branch}:{customer_number}`.

Never username alone. Existing iFilm upsert-by-username must be fixed in the implementation pass.

---

## 5. Active / inactive mapping

**Not live-verified.** After QA, map the **real** `verified` + `account_status` + `internet_status` + `expiry_date`.

Provisional (must not ship as fact):

- Sign-in / iFilm entitlement only when `verified` is true **and** internet service is usable
- Suspended / expired / disabled → deny playback; not “wrong password” if portal distinguishes them
- Missing/unknown enums → fail closed

---

## 6. Passwordless validation

**Does not exist** on `/voice-ai/v1` (404 for status/validate/assertion/token).

This is the **only** portal extension A1 should consider: `POST /api/voice-ai/v1/customers/status` with branch + `customer_number`, no password.

Interim: bounded local entitlement TTL, fail closed on new playback after expiry (re-login). Never store the Internet password.

---

## 7. Remaining portal gap

| Gap | Owner | Notes |
|-----|--------|--------|
| Issue `IFILM_PORTAL_TOKEN` + `X-Mobin-Client: ifilm` | Portal admin | Independent of 3CX |
| Confirm `/agent/config` locations (or add `/service-locations`) | Portal + iFilm QA | One small add at most |
| Confirm lookup success schema + status enums | QA with dedicated accounts | Required before mapping |
| Confirm `request_source` for iFilm | Portal | Do not invent if enumerated |
| Confirm `customer_number` uniqueness | QA | Composite subject if scoped |
| Passwordless current-status | Portal (optional for v1) | Only additive endpoint if TTL is unacceptable |
| Token scopes / authenticated rate limits | Portal | Document; prefer deny `packages/search` to iFilm |
| CORS `*` on partner API | Portal (debt) | iFilm still never puts token in JS |

**Not a gap:** inventing `/api/integrations/ifilm/authenticate`.

---

## 8. Revised A1 implementation plan

When the iFilm token and one successful QA lookup exist:

1. Backend portal HTTP client for `/api/voice-ai/v1` only (`PORTAL_IFILM_TOKEN`, `X-Mobin-Client: ifilm`).
2. Locations from `/agent/config` (or new `/service-locations`).
3. Identity mode `portal`; persist `portal_mns` + stable subject; **no** migration 024 unless extra columns are required.
4. Extend login to pass **branch**; stop username-only upsert collisions.
5. Map real lookup fields → entitlement snapshot; `ifilm_allowed` iff internet service usable (unless a real product rule appears).
6. `/login` UI: Service Location + Internet Username + Password; browser never calls portal.
7. Tests: mocked LIVE 401/405/404 shapes + mocked success from the QA payload; customer login regression; admin login unchanged.
8. Feature flag default **false**. Do not enable production until staging QA.
9. Passwordless status client only if portal adds it; otherwise TTL/fail-closed.

**This PR does not implement that yet.** Live success QA has not proven the lookup payload.

---

## iFilm identity / migration status

| Item | Status |
|------|--------|
| Attach point | `SubscriberIdentityProvider` + `subscribers` + entitlement snapshots |
| Migration `024_…` | **Not created** (not required until identity extras need it) |
| Alembic head | `023_media_tracks_packaging_v1` |
| Password persistence | Forbidden; none added |
| Admin auth | Unchanged |
| Portal client / login UI | **Not implemented** this pass |

---

## Security results

| Check | Result |
|-------|--------|
| No SAS DB from iFilm | Pass |
| No 3CX token in repo/report/logs | Pass |
| No customer passwords in repo/report | Pass |
| Voice-ai exists and is token-gated | Pass (LIVE) |
| Separate iFilm credential | **Not issued** |
| Frontend portal secret | None |

---

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/auth/VOICE_AI_V1_LIVE_CONTRACT.md` | Exact live + operator contract |
| `docs/auth/PORTAL_AUTH_AUDIT.md` | Corrected probe findings |
| `docs/auth/PORTAL_IFILM_INTEGRATION_CONTRACT.md` | Reuse-first contract |
| `docs/auth/PORTAL_AUTH_ARCHITECTURE.md` | Target iFilm design |
| `docs/auth/PORTAL_AUTH_QA.md` | QA plan |
| `docs/auth/A1_PORTAL_AUTH_REPORT.md` | This report |

Screenshots (browser login UX): `docs/auth/screenshots/a1/portal-login-desktop.png`, `portal-login-mobile.png`.

---

## Ready gate

| Gate | Status |
|------|--------|
| S2S API exists | **PASS** (`/api/voice-ai/v1`) |
| iFilm-specific token | FAIL |
| Locations from portal dynamically | FAIL (config unread) |
| Real lookup success QA | FAIL (not run) |
| Passwordless or accepted TTL policy | Partial (policy documented; API missing) |
| Never connect to SAS DB | PASS |
| Implementation + CI | N/A — not started |

**A1 Ready: NO**

---

## Next human actions

1. Portal: issue `IFILM_PORTAL_TOKEN` for `X-Mobin-Client: ifilm` (do not paste it into chat).
2. Provide dedicated QA subscriber secrets to the next implementation agent.
3. With that token: dump redacted `/agent/config` + one QA lookup (redact PII as needed) and resume A1 code.
4. Decide passwordless `/customers/status` vs TTL/fail-closed for v1.

---

## Stop

Corrected audit complete. **No merge. No deploy. No G3/T1/player work.**
