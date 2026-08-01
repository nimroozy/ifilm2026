# Backup and Recovery (Staging)

## What to back up

| Asset | Method | Notes |
| --- | --- | --- |
| PostgreSQL | `pg_dump -Fc` | Schema + data |
| Media originals | Volume tar | `staging_media_originals` |
| HLS packages | Volume tar | `staging_media_packages` |
| Environment | Copy `.env.staging` | Full (mode 600) + redacted copy for tickets |

## Backup script (verified)

```bash
./deploy/staging/scripts/backup.sh
# Output: deploy/staging/backups/<UTC-stamp>/
```

Verified artifact example (sizes vary):

- `postgres.dump` — `pg_restore -l` lists TOC (admin_*, alembic_version, …)
- `media_originals.tar.gz` — readable tar
- `media_packages.tar.gz` — readable tar (HLS packages)
- `env.staging.full` (600) / `env.staging.redacted` (secrets → `REDACTED`)
- `MANIFEST.txt`

The script does **not** upload off-host automatically.

## Restore outline (non-destructive default)

Do **not** run a destructive restore against the live staging stack unless using an isolated temporary database.

1. Stop API/workers if restoring into the same project.
2. Postgres restore example:

```bash
docker compose -f deploy/staging/docker-compose.staging.yml --env-file deploy/staging/.env.staging \
  exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < postgres.dump
```

3. Volume restore example:

```bash
VOL=$(docker volume ls -q | grep staging_media_packages | head -1)
docker run --rm -v "$VOL:/data" -v "$PWD:/in:ro" alpine:3.20 \
  sh -c 'rm -rf /data/*; tar xzf /in/media_packages.tar.gz -C /data'
```

4. Restore env carefully; rotate secrets if exposure is suspected.
5. `./deploy/staging/scripts/migrate.sh` (no-op if dump is current).
6. `./deploy/staging/scripts/ops_check.sh`

## Retention

Define host-level retention for staging snapshots. Production offsite replication (R2/S3) remains out of scope.
