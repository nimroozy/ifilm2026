# Phase: Staging deployment foundation — repository audit

**Date:** 2026-07-31  
**Branch:** `deployment/staging-foundation`  
**Base:** `main` @ Phase 11 (`b47a131`)

## Existing artifacts audited

| Item | Path / status |
| --- | --- |
| Dev compose | `docker-compose.yml` — postgres, redis, api, ARQ worker, media-processing, publishing; **no** frontend/nginx |
| Backend Dockerfile | `app/backend/Dockerfile` — root user (staging uses `Dockerfile.staging` + gosu drop to uid 10001) |
| Systemd | `app/backend/systemd/ifilm-media-processing.service` only (host path); staging prefers compose workers |
| Nginx | none previously → `deploy/staging/nginx/` |
| Env examples | `app/backend/.env.example`, `app/frontend/.env.example` |
| Media mounts (dev) | host bind `./data/media`; risk of public exposure if mis-proxied |
| Workers | media-processing + publishing in compose; ARQ worker not required for staging media path |
| Migrations | Alembic only; head `010_subscriber_entitlements`; no auto-migrate on boot |
| Health | `/api/health`, `/live`, `/ready` |
| Backup / logrotate | none previously |
| Frontend prod serving | optional `FRONTEND_DIST` on API; staging uses dedicated frontend container + edge nginx |

## Gaps closed by this milestone

- Production-like staging compose: postgres, redis, backend-api, frontend, media-processing-worker, publishing-worker, nginx
- Persistent named volumes; packages RO on API / RW on media worker; no public MEDIA_ROOT
- HTTPS-ready nginx example; upload limits/timeouts; security headers; CSP passthrough; deny `/media|/packages|/originals`
- `.env.staging.example` — fixture identity + `STAGING_ALLOW_FIXTURE_AUTH` for staging only; Radius mapping off
- Explicit `migrate.sh` (`alembic upgrade head`); optional `seed_staging.sh`; no `create_all` / no auto seed
- Backup, ops_check, smoke_test scripts + deployment docs

## Explicit non-goals

- Live SAS Radius / Cloudflare / CDN / R2 / S3 / DRM
- Phase 12 subtitles
- Automatic deploy or merge

## Remaining risks (operator)

| Severity | Finding |
| --- | --- |
| HIGH | Full E2E smoke not executed against a live host in this PR — run `ops_check` + `smoke_test` after first bring-up |
| HIGH | `DATABASE_URL` assembled from compose vars — passwords with `@:/#` need URL-encoding |
| HIGH | Smoke encode/publish may not reach package-ready without a real probeable video |
| MEDIUM | Frontend/nginx edge containers still run as root (ports 80) — acceptable for staging; document for prod hardening |
| MEDIUM | Redis has no AUTH in staging compose — bind to internal network only (compose default) |
| BLOCKER (prod) | Live Radius entitlement mapping remains unverified — keep disabled |
