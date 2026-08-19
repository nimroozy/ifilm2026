# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — MISSING SECURE CREDENTIALS
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `c141335e198b25241d5ed3544e7a30cb06ab2490`  

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**  
**Do not start G3 / T1 / player redesign.**

---

## LIVE_QA pass status (2026-08-19)

### Authorization for this pass

Owner authorized **QA-only** use of the existing Voice AI / 3CX-shaped service credential
**if supplied through the agent secure environment**. That does **not** approve production
credential sharing for iFilm.

### Credential availability in this agent

| Secret | In agent env? |
|--------|----------------|
| `PORTAL_VOICE_AI_TOKEN` | **MISSING** |
| Dedicated QA subscriber username/password/branch | **MISSING** |
| Inactive / suspended / second-branch QA accounts | **MISSING** |

No bearer token, subscriber password, or production secret was printed, logged, committed,
or written into this repository.

**Result:** Authenticated `POST /customers/lookup` LIVE_QA cases **could not be executed**.
Application behavior was **not** changed.

### LIVE probes that do not require a real token (LIVE_QA)

Against `https://portal.mns.af/api/voice-ai/v1`:

| Call | HTTP | Body (safe) |
|------|------|-------------|
| `GET /service-locations` | **404** | Laravel not-found (no dynamic JSON locations) |
| `POST /customers/lookup` with no `Authorization` + `X-Mobin-Client: 3cx-voice-agent` + `request_source=3cx_voice` | **401** | `success=false`, `code=unauthorized`, `message=Invalid or missing service token.` |
| Same with fake non-secret bearer | **401** | identical unauthorized JSON |

These confirm the lookup route still enforces a service bearer. They do **not** prove
success payload shape, entitlement enums, identity, or branch acceptance for real
subscribers.

---

## Required report items (authenticated LIVE_QA)

| # | Item | Status |
|---|------|--------|
| 1 | Active lookup HTTP status | **NOT TESTED** — no token / QA subscriber |
| 2 | Redacted active lookup JSON | **NOT CAPTURED** |
| 3 | Invalid-password behavior | **NOT TESTED** |
| 4 | Invalid-user behavior | **NOT TESTED** |
| 5 | Wrong-branch behavior | **NOT TESTED** |
| 6 | Inactive/suspended behavior | **NOT TESTED** |
| 7 | Exact `account_status` values | **UNKNOWN** |
| 8 | Exact `internet_status` values | **UNKNOWN** |
| 9 | `expiry_date` format/semantics | **UNKNOWN** |
| 10 | `customer_number` type / identity recommendation | **UNKNOWN** — keep provisional `{branch}:{username}` |
| 11 | Accepted branch representation | **UNKNOWN** for Voice AI lookup body (HTML login still embeds name+id; not authoritative for S2S) |
| 12 | Current entitlement code correct? | **UNPROVEN** — remain fail-closed; do not change |
| 13 | Change `{branch}:{username}` identity? | **UNPROVEN** — do not migrate yet |
| 14 | Application changes required | **None from this pass** (no contradicting LIVE evidence) |
| 15 | PR head SHA | Updated only for this documentation commit |

### Entitlement / identity (still PROVISIONAL — not LIVE_QA)

Until authenticated LIVE_QA succeeds:

- Do **not** treat `account_status == active` alone as proven sufficient.
- Do **not** classify `internet_status` as online/offline session state without proof.
- Do **not** ignore `expiry_date` without documented portal semantics.
- Unknown statuses remain **deny**.
- Preferred identity after QA remains `customer_number` (global or branch-scoped); current
  `{BRANCH_CODE}:{username}` stays provisional.
- Static six-location backend list remains temporary fallback; `GET /service-locations`
  still **LIVE 404**.

---

## What owner must inject for the next LIVE_QA agent pass

Supply via **secure environment / Cursor secrets only** (never repo files):

```text
PORTAL_VOICE_AI_TOKEN=<existing Voice AI bearer — QA only>
PORTAL_QA_BRANCH=<accepted branch string>
PORTAL_QA_USERNAME=<QA subscriber>
PORTAL_QA_PASSWORD=<QA password>
```

Optional for fuller matrix:

```text
PORTAL_QA_BRANCH_2 / PORTAL_QA_USERNAME_2 / PORTAL_QA_PASSWORD_2
PORTAL_QA_INACTIVE_* or PORTAL_QA_EXPIRED_*
PORTAL_QA_SUSPENDED_*
```

Then re-run the authenticated matrix in the task brief (active, bad password, bad user,
wrong branch, inactive/suspended if available, second branch if available). Redact all
secrets from reports.

---

## CI / code review context (unchanged)

- CI green on implementation tip; migration 024 reviewable in Draft only.
- `PORTAL_AUTH_ENABLED=false` by default.
- No production enablement; no merge while contract unproven.

---

## Status (authoritative)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — MISSING SECURE CREDENTIALS
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```
