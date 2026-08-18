# A1 — Portal/SAS Subscriber Authentication Report

**Status:** A1 CONTRACT / AUDIT COMPLETE — A1 IMPLEMENTATION BLOCKED ON PORTAL CREDENTIAL + QA  
**Train:** A1 (prioritized ahead of G3 / T1 / player)  
**Baseline:** production `v1.17.0`  
**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** *(updated after push)*

**Do not merge as an authentication implementation. Do not deploy. Do not start G3/T1/player redesign.**

---

## Verdict

Portal already has a partner JSON API at `https://portal.mns.af/api/voice-ai/v1` (3CX voice agent).

A1 must **reuse** `POST /customers/lookup` when iFilm-client QA succeeds. Do **not** invent `/api/integrations/ifilm/*` authenticate.

Do **not** call the whole lookup integration LIVE-verified for iFilm yet.

`GET /agent/config` is **remote voice-agent prompt/config**, not a location source.

Required portal additions are small:

| ID | Addition |
|----|----------|
| A | Dedicated iFilm service credential (verify/extend middleware if only one global token exists) |
| B | `GET /api/voice-ai/v1/service-locations` |
| C | `POST /api/voice-ai/v1/customers/status` (optional if TTL + re-login is accepted) |

iFilm login code waits on the blockers in §9.

---

## 1. Corrected lookup JSON shape (PRIOR_3CX)

Envelope: `success`, `verified`.  
Subscriber/service fields under `customer`.  
`current_package` is an object.

```json
{
  "success": true,
  "verified": true,
  "customer": {
    "display_name": "...",
    "customer_number": "...",
    "branch": "Kabul",
    "account_status": "...",
    "internet_status": "...",
    "current_package": {
      "name": "...",
      "download_speed": "...",
      "upload_speed": "..."
    },
    "expiry_date": "...",
    "days_remaining": 10
  }
}
```

Do **not** build DTOs from a flattened response.

Exact `account_status` / `internet_status` values: **require QA**.

PRIOR_3CX validation codes (HTTP 400/422; **do not show to customers**):

`invalid_branch`, `branch_rejected`, `username_rejected`, `password_rejected`

---

## 2. Corrected `/agent/config` purpose

PRIOR_3CX success (approximate):

```json
{
  "success": true,
  "version": "...",
  "instructions": "..."
}
```

Classification: **remote voice-agent configuration**.  
**Not** a confirmed location source. Do not use it for the iFilm Service Location dropdown.

---

## 3. Service locations

Known names (HTML + PRIOR_3CX) — **not** a long-term iFilm hard-code:

Kabul, Kandahar, Ghazni, Nimruz, Buldak, Helmand

No JSON locations endpoint exists (**LIVE** 404).  
Minimal portal add: `GET /api/voice-ai/v1/service-locations`.

Preferred:

```json
{
  "success": true,
  "locations": [
    { "id": "1", "name": "Kabul", "active": true }
  ]
}
```

Use actual portal fields when implemented. Never expose SAS hosts/secrets.

---

## 4. Token-model uncertainty

PRIOR_3CX proves a service **bearer exists**.

It does **not** prove portal supports multiple client-specific tokens.

Required end state:

| Client | Header | Token |
|--------|--------|--------|
| 3CX | `X-Mobin-Client: 3cx-voice-agent` | its own |
| iFilm | `X-Mobin-Client: ifilm` | **separate** |

Do not reuse the 3CX token / `MOBIN_PORTAL_AI_TOKEN`.

If middleware currently accepts only one global secret, document and implement a **small portal auth-middleware change**. Classify as: **verify / possibly extend**.

---

## 5. `request_source`

| Value | Status |
|-------|--------|
| `3cx_voice` | **Confirmed** (PRIOR_3CX) |
| `ifilm` | **UNKNOWN** — do not assume until portal accepts/documents it |

---

## 6. Passwordless status

**Not found** (LIVE 404).

Recommended: `POST /api/voice-ai/v1/customers/status`

```json
{ "branch": "Kabul", "customer_number": "..." }
```

No password. Portal queries **current** service state.

Optional for v1 only if product accepts bounded entitlement TTL + forced re-login.

---

## 7. Exact remaining portal additions

Reuse: `POST /api/voice-ai/v1/customers/lookup`.

Add (small):

1. **A** — dedicated iFilm credential support  
2. **B** — `GET /api/voice-ai/v1/service-locations`  
3. **C** — `POST /api/voice-ai/v1/customers/status` (unless TTL/re-login is explicit)

Do **not** build another authenticate endpoint.

---

## 8. Successful QA lookup

**Not run.** No iFilm credential and no QA subscriber secret in this environment. 3CX token not used.

---

## 9. Revised A1 blockers

See **Frozen portal requirements** below. Capability is PRIOR_3CX; route is LIVE; iFilm reuse is PROVISIONAL; production iFilm auth is NOT VERIFIED.

**This PR:** docs only. No application code, no migration, no login UI, no deploy.

---

## iFilm identity / migration status

| Item | Status |
|------|--------|
| Attach point | `SubscriberIdentityProvider` + `subscribers` + entitlement snapshots |
| Migration `024_…` | **Not created** |
| Alembic head | `023_media_tracks_packaging_v1` |
| Portal client / login UI | **Not implemented** |
| Admin auth | Unchanged |

---

## Ready gate (evidence classes)

| Gate | Classification |
|------|----------------|
| Existing `/customers/lookup` authentication capability | **PASS — PRIOR_3CX** |
| Route/API existence (`/api/voice-ai/v1`, including lookup) | **PASS — LIVE** |
| Reusable for iFilm | **PROVISIONAL** — pending dedicated iFilm token + successful QA lookup |
| Production iFilm authentication | **NOT VERIFIED** |
| `/agent/config` as locations | **N/A** — not a location source |
| Dynamic locations API | **FAIL** — add `/service-locations` (or another real JSON source) |
| Dedicated iFilm credential | **FAIL** (multi-token support UNKNOWN) |
| Never connect to SAS DB | **PASS** |

The lookup route is LIVE. The 3CX auth *capability* is PRIOR_3CX. The integration is **not** LIVE-verified for iFilm.

**A1 Ready: NO** — contract/audit complete; implementation blocked on portal credential + QA.

---

## Frozen portal requirements (before iFilm implementation)

**Existing and reused:** `POST /api/voice-ai/v1/customers/lookup`

Required:

1. Dedicated iFilm portal bearer
2. `X-Mobin-Client: ifilm` accepted
3. Confirmed `request_source` for iFilm
4. `GET /api/voice-ai/v1/service-locations` **or** another real dynamic JSON location source
5. One successful QA lookup
6. `customer_number` identity semantics
7. `account_status` enum
8. `internet_status` enum

**Preferred:** `POST /api/voice-ai/v1/customers/status` (passwordless current-service validation).

### If `/customers/status` is deferred for v1

Exact policy:

- Entitlement snapshot TTL = **15 minutes**
- After TTL expires, **new** protected playback is denied
- Customer must log in again
- Password is never stored
- Existing playback already issued is **not** retroactively recalled unless the current player/token architecture already supports that

---

## Stop

**A1 CONTRACT / AUDIT COMPLETE.**  
**A1 IMPLEMENTATION BLOCKED ON PORTAL CREDENTIAL + QA.**  
No merge as authentication implementation. No deploy.
