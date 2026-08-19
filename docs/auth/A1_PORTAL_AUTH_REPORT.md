# A1 — Portal/SAS Subscriber Authentication Report

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — SECRETS NOT INJECTED INTO THIS AGENT VM
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```

**Draft PR:** https://github.com/nimroozy/ifilm2026/pull/76  
**Branch:** `cursor/a1-portal-subscriber-auth-4873`  
**Head SHA:** `e2630d24e1186c84def6eed07fd90296c2f2e816`

**Do not merge. Do not deploy. Keep `PORTAL_AUTH_ENABLED=false`.**  
**Do not start G3 / T1 / player redesign.**

Classification key:

| Tag | Meaning |
|-----|---------|
| **LIVE_QA** | Observed against production portal in this agent pass |
| **PRIOR_3CX** | Historical 3CX integration evidence (not re-authenticated this pass) |
| **PROVISIONAL** | Implementation assumption — not proven by authenticated LIVE_QA |

---

## LIVE_QA resume attempt (2026-08-19)

### Authorization

Owner authorized **QA-only** use of the existing Voice AI / 3CX-shaped service credential
for authenticated LIVE_QA. That does **not** approve production credential sharing for iFilm.

### Credential visibility on this agent (resume pass)

Owner stated secure environment variables were provided. This agent VM still reports:

| Variable | Visible in process environment? |
|----------|----------------------------------|
| `PORTAL_VOICE_AI_TOKEN` | **NO** |
| `PORTAL_QA_BRANCH` | **NO** |
| `PORTAL_QA_USERNAME` | **NO** |
| `PORTAL_QA_PASSWORD` | **NO** |
| Optional inactive / second-branch QA vars | **NO** |

Diagnostics for this run (`cursor-cloud` `environment-info`):

- **Linked Cursor environment:** `null` (no dashboard environment attached to this agent)
- Therefore dashboard/environment secrets **cannot inject** into this VM

No bearer token, subscriber password, or Authorization header value was printed, logged,
committed, or written into this repository.

**Result:** Authenticated `POST /customers/lookup` LIVE_QA matrix **still could not be
executed**. Application behavior was **not** changed.

### How to unblock the next agent

1. Create or attach a **Cursor Cloud environment** for this repo that includes secrets:
   - `PORTAL_VOICE_AI_TOKEN` (required)
   - `PORTAL_QA_BRANCH` / `PORTAL_QA_USERNAME` / `PORTAL_QA_PASSWORD` (required)
   - Optional: inactive/expired/suspended and second-branch QA triples
2. **Start a new cloud agent** (or rebuild) **from that environment** so secrets are
   present in the VM process environment at boot.
3. Re-run the authenticated matrix against
   `POST https://portal.mns.af/api/voice-ai/v1/customers/lookup` with
   `X-Mobin-Client: 3cx-voice-agent` and `request_source=3cx_voice` (QA-only).

Adding secrets only in chat text or to an environment that is **not** linked to this run
will not make them visible here.

### LIVE_QA probes that do not require a real token (still valid)

Against `https://portal.mns.af/api/voice-ai/v1`:

| Call | HTTP | Body (safe) | Tag |
|------|------|-------------|-----|
| `GET /service-locations` | **404** | route not found | **LIVE_QA** |
| `POST /customers/lookup` no/fake bearer | **401** | `unauthorized` / Invalid or missing service token | **LIVE_QA** |

### LIVE_QA — portal HTML login locations (not S2S authority)

| Name | numeric `value` |
|------|-----------------|
| Kabul | `1` |
| Nimruz | `2` |
| Kandahar | `3` |
| Ghazni | `4` |
| Helmand | `5` |
| Buldak | `6` |

Does **not** prove `/customers/lookup` accepts name vs id vs code.

---

## Required report items (authenticated LIVE_QA)

| # | Question | Status |
|---|----------|--------|
| 1 | Exact successful lookup JSON structure | **NOT CAPTURED** |
| 2 | Exact `customer_number` | **UNKNOWN** |
| 3 | `customer_number` suitable as stable identity? | **UNKNOWN** |
| 4 | Exact `account_status` | **UNKNOWN** |
| 5 | Exact `internet_status` | **UNKNOWN** |
| 6 | Exact `expiry_date` value/format | **UNKNOWN** |
| 7 | Is `internet_status` session online/offline or entitlement? | **UNKNOWN** |
| 8 | Must `expiry_date` independently gate iFilm? | **UNKNOWN** |
| 9 | Exact accepted branch representation | **UNKNOWN** (HTML name+id is non-S2S **LIVE_QA**) |
| 10 | Invalid password behavior | **NOT TESTED** |
| 11 | Invalid username behavior | **NOT TESTED** |
| 12 | Wrong branch behavior | **NOT TESTED** |
| 13 | Inactive/suspended behavior | **NOT TESTED** |
| 14 | Must entitlement mapping change? | **UNPROVEN** — **do not change code** |
| 15 | Must `{branch}:{username}` identity change? | **UNPROVEN** — **do not migrate** |

### Still PROVISIONAL (not LIVE_QA)

- Entitlement: `success && verified && account_status == active` (internet_status ignored)
- Identity: `{BRANCH_CODE}:{username}`
- Locations: static backend six-name list (temporary fallback)
- Credential: 3CX-shaped client/source for production iFilm

Unknown statuses remain **deny**. No application behavior changes until authenticated
LIVE_QA contradicts a specific assumption with redacted evidence.

---

## Status (authoritative)

```text
A1 CODE: READY FOR HUMAN REVIEW
A1 CI: PASS
A1 PORTAL CONTRACT: PROVISIONAL
A1 LIVE QA: BLOCKED — SECRETS NOT INJECTED INTO THIS AGENT VM
A1 PRODUCTION READY: NO
A1 MERGE: BLOCKED ON LIVE PORTAL QA / OWNER DECISIONS
```
