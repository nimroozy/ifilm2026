# Phase 11 — Subscriber Authentication & Entitlements Audit

**Date:** 2026-07-31  
**Base:** `main` @ `675b7df4c87e6504fdf5b51d6252f324e95826c4` (Phase 10 squash)  
**Branch:** `subscriber/auth-entitlements`  
**Alembic head before Phase 11:** `009_watch_history`

---

## Direct answers

| Question | Finding |
| --- | --- |
| Subscriber auth production-ready? | **No** — fixture/mock path verified; live Radius unverified |
| Radius login safe for production? | **No** — attribute mapping, entitlement semantics, failover unverified |
| Local subscriber records? | **Yes** — `subscribers` table mirrored on login |
| External subscriber ID? | **None today** — username used as correlation; JWT `sub` = local int |
| Branches/packages trusted entitlement? | **No** — display strings only; not authorization |
| Entitlement today? | Active local subscriber + published catalog + active HLS; **no** package/expiry check |
| Subscriber → admin APIs? | **Denied** (`typ` isolation tested) |
| Refresh rotation for subscribers? | **None** — access JWT only; logout is no-op server-side |
| Device limits? | **Mocked** — unused DB stub + frontend fixtures |
| Profile fields? | Partial API (`/auth/me`); devices/counts/status mock or hard-coded |
| Live SAS assumptions? | Explicitly **unverified** in docs |

## Current auth flow gaps

- `POST /api/auth/login` requires `ENABLE_RADIUS_LOGIN`; stores Radius password hash locally (unnecessary)
- Successful Access-Accept forces local `status=active` (can un-suspend)
- No refresh tokens / revocation / rate limiting
- Playback eligibility ignores package expiry and provider status
- Devices table unused; watch progress `device_id` not validated

## Phase 11 decisions

1. Introduce `SubscriberIdentityProvider` with fixture (dev/test only) and Radius adapter (fail-closed).
2. Migration `010_subscriber_entitlements`: entitlement snapshots, device sessions, refresh tokens; extend subscribers with provider + external subject.
3. Stop storing Radius passwords; clear hashes for provider-backed accounts.
4. Entitlement service: allow only with fresh allowed snapshot; expired/missing/unknown → deny.
5. Device limits with app-generated client device ID; revoke cascades to refresh + playback sessions.
6. Distinct subscriber auth routes under `/api/auth/subscriber/*`; keep `/api/auth/login` as compatibility alias.
7. Admins retain operational playback bypass (documented); subscribers require entitlement.
8. Do **not** claim live SAS verification unless staging-tested (remain documented as unverified).

## Deferred

Online payments, billing, plan purchase, auto-renewal, Cloudflare/CDN/R2/S3, DRM, recommendations, analytics, subtitles, offline, TV apps, Phase 12.
