# Backup and Recovery (Staging)

## What to back up

| Asset | Method | Notes |
| --- | --- | --- |
| PostgreSQL | `pg_dump -Fc` | Schema + data; includes catalog, auth, watch progress |
| Media originals | Volume tar | Source uploads under `staging_media_originals` |
| HLS packages | Volume tar | Completed packages under `staging_media_packages` |
| Environment | Copy `.env.staging` | Treat as secret; keep redacted copy for tickets |

Artwork under `staging_artwork` can be regenerated or backed up similarly if non-empty.

## Backup script

```bash
./deploy/staging/scripts/backup.sh
# Output: deploy/staging/backups/<UTC-stamp>/
```

Artifacts:

- `postgres.dump`
- `media_originals.tar.gz`
- `media_packages.tar.gz`
- `env.staging.full` (mode 600)
- `env.staging.redacted`
- `MANIFEST.txt`

Copy the backup directory to off-host durable storage. The script does **not** upload automatically.

## Restore outline

1. Stop API/workers (`docker compose … stop backend-api media-processing-worker publishing-worker`).
2. Restore Postgres:

```bash
docker compose -f deploy/staging/docker-compose.staging.yml --env-file deploy/staging/.env.staging \
  exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < postgres.dump
```

3. Restore volumes (example for packages):

```bash
VOL=$(docker volume ls -q | grep staging_media_packages | head -1)
docker run --rm -v "$VOL:/data" -v "$PWD:/in:ro" alpine:3.20 \
  sh -c 'rm -rf /data/*; tar xzf /in/media_packages.tar.gz -C /data'
```

4. Restore env file carefully; rotate secrets if the backup may have been exposed.
5. Run `./deploy/staging/scripts/migrate.sh` (should be no-op if dump is current).
6. Start services and run `ops_check.sh`.

## Retention

Define host-level retention (e.g. 14 daily staging snapshots). Document longer retention separately for production when that environment exists.

## Out of scope

- Continuous WAL shipping
- Object-storage offsite replication (R2/S3 deferred)
- Automatic restore drills (schedule manually)
