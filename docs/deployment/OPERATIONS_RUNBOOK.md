# Operations Runbook (Staging)

## Bring-up

1. Fill `deploy/staging/.env.staging` from `.env.staging.example` (chmod 600).
2. `docker compose -f deploy/staging/docker-compose.staging.yml --env-file deploy/staging/.env.staging up -d --build`
3. `./deploy/staging/scripts/migrate.sh`
4. Optional: `./deploy/staging/scripts/seed_staging.sh`
5. `./deploy/staging/scripts/ops_check.sh`

## Health endpoints

| Path | Expect |
| --- | --- |
| `GET /healthz` | nginx `ok` |
| `GET /api/health` / `/api/health/live` | 200 |
| `GET /api/health/ready` | 200 when Postgres + Redis OK |

Worker health: compose healthchecks on `media-processing-worker` (ffmpeg/ffprobe) and `publishing-worker` (DB connect).

## Common failures

| Symptom | Action |
| --- | --- |
| Startup rejects fixture | Ensure `APP_ENV=staging` and `STAGING_ALLOW_FIXTURE_AUTH=true`; never enable in production |
| Startup rejects Radius | Keep `RADIUS_ENTITLEMENT_MAPPING_ENABLED=false` and do not set identity mode to `radius` |
| Ready 503 | Check postgres/redis health; `docker compose logs` |
| Upload 413 | nginx `client_max_body_size` / `UPLOAD_MAX_BYTES` |
| Encode stuck | media-processing-worker logs; disk space on packages volume |
| Playback 403 after unpublish | Expected |

## Disk space

```bash
df -h
docker system df
./deploy/staging/scripts/ops_check.sh
```

Clean unused images carefully; never delete named staging volumes without a backup.

## Logs

Containers log to stdout. Use:

```bash
docker compose -f deploy/staging/docker-compose.staging.yml --env-file deploy/staging/.env.staging logs -f --tail=200
```

Optional host logrotate example: `deploy/staging/logrotate/ifilm-staging.example`.

## Backups

See [BACKUP_AND_RECOVERY.md](./BACKUP_AND_RECOVERY.md). Run `backup.sh` before risky migrations or media cleanups.

## Smoke test

```bash
ADMIN_PASS='…' SUB_PASS='…' STAGING_BASE_URL=http://127.0.0.1:8080 \
  ./deploy/staging/scripts/smoke_test.sh
```

Covers: admin login, fixture subscriber login, device limit, movie create, upload path, probe/encode best-effort, publish best-effort, playback, watch history, unpublish denial.

## Hard rules

- Do **not** enable live SAS Radius on this stack.
- Do **not** enable Cloudflare / CDN / R2 / S3 / DRM here.
- Do **not** begin Phase 12 subtitles until staging verification passes.
- Do **not** merge/deploy automatically from this foundation PR alone without operator review.
