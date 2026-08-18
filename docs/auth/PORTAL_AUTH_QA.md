# A1 Portal Auth QA Plan

**Status:** Planned — blocked on portal integration contract  
**Production site:** https://ifilm.af  
**Portal:** https://portal.mns.af

Do not use real customer passwords in screenshots or committed reports.

---

## 1. Preconditions

- [ ] Portal integration endpoints live per `PORTAL_IFILM_INTEGRATION_CONTRACT.md`
- [ ] Partner credential issued to iFilm staging/prod secrets
- [ ] Dedicated QA subscribers:
  - Location A active
  - Location A wrong-password control
  - Location B active (same username if possible)
  - Inactive/suspended account if available

---

## 2. Portal contract QA (before iFilm UI)

| # | Case | Expected |
|---|------|----------|
| P1 | Locations with partner auth | 200, active locations only, no secrets |
| P2 | Locations without partner auth | 401/403 |
| P3 | Authenticate valid QA A | authenticated + active + ifilm_allowed |
| P4 | Wrong password | generic invalid credentials |
| P5 | Wrong location | generic invalid / denied (no enumeration) |
| P6 | Inactive account | service inactive |
| P7 | Duplicate username A vs B | distinct subjects unless portal stable id says same |
| P8 | Validate with assertion | success without password |
| P9 | Validate expired assertion | deny |
| P10 | Portal timeout simulation | iFilm fails closed |

---

## 3. iFilm login QA

| # | Case | Expected |
|---|------|----------|
| I1 | Locations load via `/api/auth/isp/locations` | dynamic from portal |
| I2 | Valid login | iFilm session issued |
| I3 | Relogin | same local subscriber id |
| I4 | Watchlist survives | yes |
| I5 | Continue Watching survives | yes |
| I6 | Progress survives | yes |
| I7 | Protected playback | requires entitlement |
| I8 | Rate limit | 429 after threshold |
| I9 | Portal outage | locations retry + login deny |
| I10 | Admin login | unchanged |
| I11 | Password absent from DB/logs/localStorage | verified |
| I12 | Secret absent from frontend bundle | scan clean |

---

## 4. Visual QA matrix

Desktop: 1440×900 EN/FA/PS  
Mobile: 390×844 EN/FA/PS, 430×932 EN

Checks: location dropdown, keyboard, touch, RTL, errors, loading, disabled submit, no overflow.

---

## 5. Audit probes already completed (2026-08-18)

| Probe | Result |
|-------|--------|
| Portal login page UX | Location + Internet Username + Password present |
| Branches in HTML | Kabul, Nimruz, Kandahar, Ghazni, Helmand, Buldak |
| `POST /api/customer/login` invalid user | 401 generic message |
| Integration endpoints | **404 / missing** |

Screenshots: `docs/auth/screenshots/a1/portal-login-desktop.png`, `portal-login-mobile.png`.

Real portal→SAS success QA: **NOT RUN** (no QA subscriber credentials in this pass; S2S contract missing).
