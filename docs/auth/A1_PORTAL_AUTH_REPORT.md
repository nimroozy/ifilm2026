# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```

**Train:** A1  
**Baseline:** production `v1.17.0` (unchanged)  
**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `cf5c70a93226228a210c903230d4fbf18f4455a0`

**Do not merge. Do not deploy. Do not start G3 / T1 / player redesign.**  
**Keep `PORTAL_AUTH_ENABLED=false` by default. No production portal secret committed.**

---

## What CI accepted

Backend, Installer, and Frontend CI are green on this tip. Migration 024 correctness,
portal identity uniqueness, and feature-off defaults are acceptable **for review only**.

Migration 024 may remain in the Draft PR for review, but **must not be merged** while
the final external identity contract is still unverified.

---

## Provisional assumptions (NOT production-approved)

Human review found four unproven assumptions. Treat each as **provisional** until live
portal QA / owner decisions close it.

### 1. Portal service credential — PROVISIONAL

Current defaults (configurable env only):

```text
PORTAL_VOICE_AI_CLIENT=3cx-voice-agent
PORTAL_REQUEST_SOURCE=3cx_voice
existing Voice AI bearer (PORTAL_VOICE_AI_TOKEN)
```

This is **not** the final production A1 contract.

Production remains blocked until either:

- **A.** Portal supports a dedicated iFilm credential (`X-Mobin-Client: ifilm`, dedicated
  bearer, confirmed iFilm `request_source`), **or**
- **B.** The owner **explicitly** approves temporary credential sharing.

Do **not** silently classify the existing 3CX credential as approved for iFilm.

### 2. Service locations — TEMPORARY FALLBACK

The centralized backend static list is acceptable only as a **temporary implementation
fallback / test fixture**. It is **not** the final authoritative production source.

Production requirement remains a real dynamic portal JSON source, preferably:

```text
GET /api/voice-ai/v1/service-locations
```

Do not duplicate the list in frontend code. Keep the backend abstraction so a dynamic
provider can replace the static source without UI changes.

### 3. External identity — PROVISIONAL

Current implementation:

```text
provider = portal_mns
external_subject = {BRANCH_CODE}:{username}
```

Do **not** claim username is the final stable identity. Live QA must determine
`customer_number` semantics.

Preferred final shapes (after QA):

```text
if customer_number globally unique:
    portal_mns:<customer_number>   # or equivalent subject form

if branch scoped:
    portal_mns:<branch>:<customer_number>
```

Retain `branch:username` only if portal QA explicitly establishes that username is the
correct stable immutable subscriber identifier. Watchlist, progress, and Continue
Watching continuity depend on this choice.

### 4. Entitlement mapping — PROVISIONAL ONLY

Current rule:

```text
success && verified && account_status == "active"
```

with `internet_status` ignored — is **provisional only**.

Do **not** classify `internet_status` as merely RADIUS online/offline without proof.
Live QA must establish actual meanings of `account_status`, `internet_status`, and
`expiry_date`.

Until proven:

- unknown status ⇒ deny
- do not assume `internet_status` is irrelevant
- do not assume `account_status=active` alone is sufficient
- do not ignore an expired `expiry_date` without documented portal semantics
- do not invent enum mappings

---

## Feature-off / secrets

| Control | Required state |
|---------|----------------|
| `PORTAL_AUTH_ENABLED` | `false` by default |
| Production enablement | Forbidden until QA + owner decisions |
| Portal bearer in repo / frontend | Forbidden |
| Deploy from this PR | Forbidden |

---

## Required live QA before approval

Redact passwords and bearer tokens from all reports.

1. Successful active subscriber lookup  
2. Invalid password lookup  
3. Inactive/expired subscriber lookup  
4. Preferably suspended subscriber lookup  
5. Exact `account_status` values  
6. Exact `internet_status` values  
7. Exact `expiry_date` behavior  
8. Returned `customer_number`  
9. `customer_number` uniqueness/stability across branches  
10. Accepted iFilm client / `request_source`  
11. Dynamic service-location source  

---

## Status (authoritative)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```
