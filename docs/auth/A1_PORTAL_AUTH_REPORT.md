# A1 — Portal/SAS Subscriber Authentication Report

**Status:** STOPPED AT CONTRACT BOUNDARY — awaiting portal integration API  
**Train:** A1 (prioritized ahead of G3 / T1 / player)  
**Baseline:** production `v1.17.0`  
**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `312d144b354ab13276c8c7e34de368b63fa60c17`

**Do not merge. Do not deploy. Do not start G3/T1/player redesign.**

---

## Verdict

Portal customer login UX already matches the business requirement (Service Location + Internet Username + Password).

iFilm **must not** talk to SAS DBs directly.

A dedicated **server-to-server iFilm integration API on portal.mns.af was not found**.

Therefore A1 implementation is **blocked** until portal delivers the contract in `PORTAL_IFILM_INTEGRATION_CONTRACT.md`.

---

## Portal API contract discovered

### Exists (live)

| Endpoint | Result |
|----------|--------|
| `GET /login` | HTML login; branches embedded as `<option value="{branch_id}">` |
| `POST /api/customer/login` | Requires `branch_id`, `username`, `password`; invalid → `401` generic message |
| `GET /api/customer/service` | Exists; `401 Unauthenticated` without session |
| `GET /api/customer/invoices` | Exists; `401 Unauthenticated` without session |

### Missing (live)

| Preferred endpoint | Status |
|--------------------|--------|
| `GET /api/integrations/ifilm/service-locations` | **404** |
| `POST /api/integrations/ifilm/authenticate` | **404** |
| `POST /api/integrations/ifilm/validate` | **404** |
| Partner/service credential auth for iFilm | **Not discovered** |
| Public JSON locations API | **Not discovered** |
| Passwordless entitlement validate | **Not discovered** |
| Documented success schema / stable subscriber id | **Unknown** |

### Location API result

- **Not available as JSON API.**
- HTML-embedded branches observed: Kabul(1), Nimruz(2), Kandahar(3), Ghazni(4), Helmand(5), Buldak(6).
- Must not be hard-coded into iFilm as the long-term source.

### Auth API result

- Browser-oriented `POST /api/customer/login` validates required fields and returns generic invalid-credential errors.
- Success response / entitlement fields: **not observed** (no QA subscriber credentials used; S2S contract missing).
- Not accepted as production iFilm S2S integration without portal changes (CSRF/session model).

---

## iFilm identity / migration status

| Item | Status |
|------|--------|
| Existing attach point | `SubscriberIdentityProvider` + `subscribers` + entitlement snapshots |
| New `external_subscriber_identities` migration | **Not created** (blocked) |
| Alembic head remains | `023_media_tracks_packaging_v1` |
| Password persistence | N/A this pass — design forbids storage |
| Admin auth changes | None |

---

## Real portal/SAS QA

| Case | Class | Result |
|------|-------|--------|
| Portal login page UX | REAL | Pass (screenshots) |
| Invalid JSON login probe | REAL | `401 Invalid username or password.` |
| Valid active subscriber login via S2S | — | **Blocked / not run** |
| Wrong password / wrong location / inactive | — | **Blocked / not run** (need contract + QA accounts) |
| Duplicate username across locations | — | **Blocked / not run** |

---

## Security results (this pass)

| Check | Result |
|-------|--------|
| No SAS DB connection from iFilm | Pass (not implemented; forbidden) |
| No portal secrets in frontend | Pass (none exist) |
| No real customer passwords in repo/report | Pass |
| Invalid login enumeration message on portal | Generic 401 message observed |
| Rate limiting / entitlement validate / bundle scan | N/A until implementation |

---

## Screenshots

- `docs/auth/screenshots/a1/portal-login-desktop.png`
- `docs/auth/screenshots/a1/portal-login-mobile.png`

---

## Documentation delivered

| Doc | Purpose |
|-----|---------|
| `docs/auth/PORTAL_AUTH_AUDIT.md` | Live probe findings |
| `docs/auth/PORTAL_IFILM_INTEGRATION_CONTRACT.md` | Exact API portal must provide |
| `docs/auth/PORTAL_AUTH_ARCHITECTURE.md` | Target iFilm design |
| `docs/auth/PORTAL_AUTH_QA.md` | QA plan when unblocked |
| `docs/auth/A1_PORTAL_AUTH_REPORT.md` | This report |

---

## Remaining findings

| Level | Finding |
|-------|---------|
| **BLOCKER (external)** | Portal missing iFilm S2S locations/authenticate/validate + partner auth |
| INFO | Existing `/api/customer/login` proves internal capability but is browser/CSRF oriented |
| INFO | Branch list currently HTML-embedded only |

No iFilm code HIGH/BLOCKER from partial implementation — implementation intentionally not started past the boundary.

---

## Ready gate

| Gate | Status |
|------|--------|
| Locations from portal dynamically | FAIL (no API) |
| No hardcoded locations | PASS (not implemented) |
| Never connect to SAS DB | PASS |
| Real portal/SAS auth success | FAIL (blocked) |
| CI / ENFA/PS / migration / feature regression | N/A — stopped |

**A1 Ready: NO**

---

## Next human actions

1. Portal team implements `PORTAL_IFILM_INTEGRATION_CONTRACT.md`.
2. Issue partner credentials to iFilm secrets.
3. Provide dedicated QA subscribers (never production customer passwords in reports).
4. Resume A1 implementation Draft PR (client + identity migration + login UI + tests).

---

## Stop

Awaiting portal contract. **No merge. No deploy. No G3/T1/player work.**
