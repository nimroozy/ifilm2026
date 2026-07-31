# Phase: Staging deployment foundation — audit + verification

**Branch:** `deployment/staging-foundation`  
**Base:** `main` @ Phase 11

## Gaps closed

- Staging compose with nginx + frontend + workers
- Non-root API/workers via gosu after volume chown
- Encoded DATABASE_URL/REDIS_URL (passwords with `@:/#`)
- Redis requirepass
- Explicit migrate / staging seed / backup / ops / smoke
- Staging fixture opt-in without allowing production fixture
- Publishing + media workers call `get_engine()` before sessions
- Alembic safe with percent-encoded passwords

## Verification (this milestone)

| Check | Result |
| --- | --- |
| Compose config | OK |
| Service health | all healthy |
| migrate → `010_subscriber_entitlements` | OK |
| ops_check | PASSED |
| smoke_test (real 45s H.264/AAC) | PASSED |
| HLS renditions | 240p, 360p |
| Backup + pg_restore -l | OK |
| Log secret scan | no hits |
| Stack left running | yes (`http://127.0.0.1:8080`) |

## Explicit non-goals

- Live SAS Radius / Cloudflare / CDN / R2 / S3 / DRM
- Phase 12 subtitles
- Automatic deploy or merge

## Remaining BLOCKER

Live Radius entitlement mapping unverified — keep disabled in production.
