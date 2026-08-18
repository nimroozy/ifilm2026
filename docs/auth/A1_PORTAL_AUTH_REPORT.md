# A1 — Portal/SAS Subscriber Authentication Report

**Status:** A1 IMPLEMENTATION: READY FOR HUMAN REVIEW  
**Train:** A1  
**Baseline:** production `v1.17.0` (unchanged — do not deploy from this PR alone without ops enablement)  
**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** *(updated after push)*

**Do not merge/deploy automatically. Do not start G3/T1/player redesign.**

---

## Implementation summary

iFilm now authenticates Internet subscribers via the **existing** portal Voice AI API:

`POST https://portal.mns.af/api/voice-ai/v1/customers/lookup`

using `Authorization: Bearer <PORTAL_VOICE_AI_TOKEN>`, `X-Mobin-Client: 3cx-voice-agent`, `request_source=3cx_voice`.

No new portal authenticate endpoint. No separate iFilm portal credential in this pass.

### iFilm routes

| Method | Path |
|--------|------|
| `GET` | `/api/auth/isp/locations` |
| `POST` | `/api/auth/isp/login` |

### Identity

`provider=portal_mns`, `external_subject={CODE}:{username}` (e.g. `NMZ:1210000`).

Migration **024** required: drop global UNIQUE on `subscribers.username`.

### Entitlement

Allow when `success && verified && account_status == "active"`.  
Ignore `internet_status` (offline ≠ inactive).  
15-minute snapshot TTL; password never stored; re-login after TTL for new protected playback.

### Login UI

Service Location + Internet Username + Password; EN / FA / PS with `dir` RTL.

### Tests (automated)

- Backend `tests/test_portal_isp_auth.py` — pass
- Frontend `subscriberAuth.test.tsx` — pass
- Related subscriber/radius tests — pass

### Remaining ops blockers (not code)

1. Set production/staging secrets: `PORTAL_AUTH_ENABLED=true`, `SUBSCRIBER_IDENTITY_MODE=portal`, `PORTAL_VOICE_AI_TOKEN=…`
2. Run migration 024 on deploy
3. Human staging QA with real portal credential (token not in this environment)

**A1 IMPLEMENTATION: READY FOR HUMAN REVIEW**
