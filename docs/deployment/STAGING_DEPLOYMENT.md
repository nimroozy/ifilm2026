# Staging Deployment

**Status:** foundation only — do **not** treat as production-ready.  
**Do not** auto-deploy. **Do not** enable live SAS Radius, Cloudflare, CDN, R2, S3, or DRM.  
**Do not** begin Phase 12 (subtitles) until staging verification passes.

## Audit summary (pre-work)

| Area | Finding |
| --- | --- |
| Dev `docker-compose.yml` | postgres, redis, api, ARQ worker, media-processing, publishing |
| Frontend container | missing (added in staging compose) |
| Nginx | missing (added) |
| Migrations on boot | not automatic — explicit `migrate.sh` |
| Backup / runbook | missing (added under `docs/deployment/`) |
| Non-root API image | staging Dockerfile uses uid 10001 |
| Fixture auth | staging opt-in via `STAGING_ALLOW_FIXTURE_AUTH`; production still forbidden |

## Layout

```
deploy/staging/
  docker-compose.staging.yml
  .env.staging.example
  nginx/
  scripts/{migrate,seed_staging,backup,ops_check,smoke_test}.sh
  logrotate/ifilm-staging.example
app/backend/Dockerfile.staging
app/frontend/Dockerfile.staging
```

## Services

| Service | Role |
| --- | --- |
| `postgres` | Persistent DB (`staging_pg_data`) |
| `redis` | AOF/RDB persistent (`staging_redis_data`) |
| `backend-api` | FastAPI; packages volume **read-only** |
| `frontend` | Built SPA (nginx alpine) |
| `media-processing-worker` | Probe/HLS; packages **read-write**, originals **RO** |
| `publishing-worker` | Schedule/publish worker; packages+originals **RO** |
| `nginx` | Public HTTP front door (HTTPS-ready example included) |

## Volume layout

| Volume | API | Media worker | Publishing | Public nginx |
| --- | --- | --- | --- | --- |
| `staging_media_originals` | RW | RO | RO | **not mounted** |
| `staging_media_temp` (+ trailers/subtitles/posters/backdrops) | RW | — | — | **not mounted** |
| `staging_media_packages` | **RO** | **RW** | RO | **not mounted** |
| `staging_artwork` | RW | — | — | via `/artwork` API only |
| `staging_pg_data` / `staging_redis_data` | — | — | — | — |

There is **no** public `MEDIA_ROOT` mount through nginx. Paths `/media/`, `/packages/`, `/originals/` return 404.

## Quick start (manual)

```bash
cp deploy/staging/.env.staging.example deploy/staging/.env.staging
# Edit REPLACE_* secrets; chmod 600 deploy/staging/.env.staging

docker compose -f deploy/staging/docker-compose.staging.yml \
  --env-file deploy/staging/.env.staging config -q

docker compose -f deploy/staging/docker-compose.staging.yml \
  --env-file deploy/staging/.env.staging up -d --build

./deploy/staging/scripts/migrate.sh
./deploy/staging/scripts/seed_staging.sh   # optional, explicit
./deploy/staging/scripts/ops_check.sh

ADMIN_PASS='…' SUB_PASS='…' ./deploy/staging/scripts/smoke_test.sh
```

## Migrations

- **Only** `alembic upgrade head` via `scripts/migrate.sh`
- **No** `create_all`
- **No** automatic demo seed
- Optional: `scripts/seed_staging.sh` → `python -m scripts.seed_dev`

## Environment highlights

| Variable | Staging intent |
| --- | --- |
| `APP_ENV` | `staging` |
| `SUBSCRIBER_IDENTITY_MODE` | `fixture` |
| `STAGING_ALLOW_FIXTURE_AUTH` | `true` (staging only) |
| `RADIUS_ENTITLEMENT_MAPPING_ENABLED` | `false` |
| `ENABLE_UPLOADS` / `ENABLE_MEDIA_PROCESSING` / `ENABLE_HLS_ENCODING` / `ENABLE_LOCAL_STREAMING` | `true` |
| Live Radius / CDN / R2 / S3 / DRM | **off** |

Production must never set `STAGING_ALLOW_FIXTURE_AUTH` or fixture identity mode.

## HTTPS

Use `nginx/ifilm.https.conf.example` after mounting certificates. HTTP config is the default for local staging bring-up.

## Related docs

- [BACKUP_AND_RECOVERY.md](./BACKUP_AND_RECOVERY.md)
- [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md)
- [../auth/SUBSCRIBER_AUTHENTICATION.md](../auth/SUBSCRIBER_AUTHENTICATION.md)
