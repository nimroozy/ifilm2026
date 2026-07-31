# Operations Runbook (Staging)

## Bring-up

1. `FORCE_STAGING_ENV=1 ./deploy/staging/scripts/prepare_env.sh` (or fill `.env.staging` manually; chmod 600).
2. `unset APP_ENV` before compose if the host shell sets `APP_ENV=test`.
3. `docker compose -f deploy/staging/docker-compose.staging.yml --env-file deploy/staging/.env.staging up -d --build`
4. `./deploy/staging/scripts/migrate.sh`
5. Optional: `./deploy/staging/scripts/seed_staging.sh`
6. `./deploy/staging/scripts/ops_check.sh`

## Health endpoints

| Path | Expect |
| --- | --- |
| `GET /healthz` | nginx `ok` |
| `GET /api/health/live` | 200 |
| `GET /api/health/ready` | 200 when Postgres + Redis OK |
| `GET /media/`, `/packages/`, `/originals/` | 404 |

Worker health: compose healthchecks source `/run/ifilm/runtime.env`.

## Ops check (verified)

`./deploy/staging/scripts/ops_check.sh` → **`ops_check: PASSED`**

Covers: compose config, service list, HTTP ready, public path deny, Alembic heads+current, Postgres, encoded DATABASE_URL connect (`@:/#` password), Redis, FFmpeg/ffprobe, mount RW/RO policy, disk, workers, Radius safety flags.

## Smoke test (verified)

```bash
./deploy/staging/scripts/smoke_test.sh
# → smoke_test: PASSED
```

Uses a real 640×360 H.264/AAC ~45s lavfi video. Does not skip encode/playback.

## Common failures

| Symptom | Action |
| --- | --- |
| `APP_ENV=test` inside containers | Host `APP_ENV` overrode compose; unset it. Compose now forces `APP_ENV: staging` |
| Password missing `#` | Quote `POSTGRES_PASSWORD='…'` in `.env.staging` |
| Alembic ConfigParser `%` error | Fixed via `create_engine` in `alembic/env.py` |
| Worker `UnboundExecutionError` | Workers must call `get_engine()` before `SessionLocal()` |
| Probe stuck queued | Check media-processing-worker logs |
| Continue Watching empty | Position must be ≥30s and less than media duration |
| Duplicate upload 409 | Smoke regenerates unique drawtext checksums |
| Startup rejects fixture | `APP_ENV=staging` + `STAGING_ALLOW_FIXTURE_AUTH=true` |

## Logs

```bash
docker compose -f deploy/staging/docker-compose.staging.yml \
  --env-file deploy/staging/.env.staging logs -f --tail=200
```

After verification, a log scan found **no** password/JWT/playback-token/DATABASE_URL credential leaks in recent container logs.

## Backups

See [BACKUP_AND_RECOVERY.md](./BACKUP_AND_RECOVERY.md).

## Hard rules

- Do **not** enable live SAS Radius on this stack.
- Do **not** enable Cloudflare / CDN / R2 / S3 / DRM here.
- Do **not** begin Phase 12 subtitles until staging verification is accepted.
- After successful verification: prefer `docker compose stop` over `down -v` (keep volumes).

## Stack state after this verification

**Running** at `http://127.0.0.1:8080` with persistent named volumes retained.
