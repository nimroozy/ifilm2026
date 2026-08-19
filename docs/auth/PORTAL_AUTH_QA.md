# A1 Portal Auth QA Plan

**Status:** A1 CONTRACT / AUDIT COMPLETE — implementation blocked on portal credential + QA  
**Production site:** https://ifilm.af  
**Portal:** https://portal.mns.af

Do not use real customer passwords or the 3CX bearer in screenshots or committed reports.  
Do not configure iFilm with `MOBIN_PORTAL_AI_TOKEN`.

---

## 1. Preconditions

- [ ] Dedicated iFilm portal token (`X-Mobin-Client: ifilm`)
- [ ] Dedicated QA subscribers (secrets store only):
  - Location A active
  - Location A wrong-password control
  - Location B active (same username if possible)
  - Inactive/suspended/expired if available
- [ ] `GET /api/voice-ai/v1/service-locations` live (do not treat `/agent/config` as locations)

---

## 2. Portal contract QA (before iFilm UI)

| # | Case | Expected |
|---|------|----------|
| P0 | Lookup/config **without** token | `401` `unauthorized` (LIVE — done) |
| P1 | `GET /service-locations` with iFilm credential | 200; active locations only; no SAS secrets |
| P2 | `GET /agent/config` | Voice-agent `version`/`instructions` — **not** used for locations |
| P3 | 3CX token from iFilm | Must not be used |
| P4 | `POST /customers/lookup` valid QA A | nested `customer`; `success`+`verified`; no secrets |
| P5 | Wrong password / branch / username | portal may return `password_rejected` etc.; iFilm UI stays generic |
| P6 | Inactive/expired/suspended | distinguishable from bad password if portal supports it |
| P7 | Duplicate username A vs B | distinct subjects unless same `customer_number` globally |
| P8 | Passwordless status | **missing today** — skip or test new `/customers/status` |
| P9 | `request_source` | `3cx_voice` confirmed; iFilm value UNKNOWN — do not assume `ifilm` |
| P10 | Rate limit | document authenticated headers; iFilm still rate-limits login |

---

## 3. iFilm login QA (implementation pass)

| # | Case | Expected |
|---|------|----------|
| I1 | Locations via `/api/auth/isp/locations` | dynamic from portal |
| I2 | Valid login | iFilm session issued |
| I3 | Relogin | same local subscriber id |
| I4–I6 | Watchlist / CW / progress | survive |
| I7 | Protected playback | requires mapped entitlement |
| I8 | Rate limit | 429 after threshold |
| I9 | Portal outage | login deny |
| I10 | Admin login | unchanged |
| I11 | Password absent from DB/logs/localStorage | verified |
| I12 | Secret absent from frontend bundle | scan clean |

---

## 4. Visual QA matrix

Desktop: 1440×900 EN/FA/PS  
Mobile: 390×844 EN/FA/PS, 430×932 EN

Checks: location dropdown, keyboard, touch, RTL, errors, loading, disabled submit, no overflow.

---

## 5. Probes completed (2026-08-18)

| Probe | Result |
|-------|--------|
| Portal login page UX | Location + Internet Username + Password present |
| HTML branches | Kabul, Nimruz, Kandahar, Ghazni, Helmand, Buldak |
| `POST /api/customer/login` invalid user | 401 generic message |
| `GET /api/voice-ai/v1/agent/config` no token | **401** `unauthorized` (route exists) |
| `POST /api/voice-ai/v1/customers/lookup` no token | **401** `unauthorized` (route exists) |
| `POST /api/voice-ai/v1/packages/search` no token | **401** `unauthorized` |
| Passwordless `/customers/status` or `/validate` | **404** |
| `/api/integrations/ifilm/*` | 404 (not the integration surface) |
| Successful QA lookup | **NOT RUN** (no iFilm token / QA secret) |

Screenshots: `docs/auth/screenshots/a1/portal-login-desktop.png`, `portal-login-mobile.png`.
