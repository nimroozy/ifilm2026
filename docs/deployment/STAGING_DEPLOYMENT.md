# Staging Deployment

**Status:** verified on this branch (compose bring-up + ops_check + full smoke).  
**Do not** enable live SAS Radius, Cloudflare, CDN, R2, S3, or DRM.  
**Do not** begin Phase 12 (subtitles) until product sign-off after this staging milestone.  
**PR remains Draft until Ready for Review is set after verification; do not auto-merge.**

## Access

| Item | Value |
| --- | --- |
| Local staging URL | `http://127.0.0.1:8080` (nginx → frontend + `/api`) |
| Compose project | `ifilm-staging` |
| Env file | `deploy/staging/.env.staging` (gitignored; create via `prepare_env.sh`) |
| Stack state after verification | **left running** (volumes retained; do not `down -v` unless resetting) |

## Quick start (commands executed)

```bash
# 1) Secrets (no REPLACE_* placeholders; POSTGRES_PASSWORD quoted and includes @:/#)
FORCE_STAGING_ENV=1 ./deploy/staging/scripts/prepare_env.sh

# 2) Real test video (640x360 H.264/AAC ~45s; never commit)
./deploy/staging/scripts/generate_test_video.sh

# 3) Fresh bring-up (only when intentionally resetting)
unset APP_ENV   # host APP_ENV=test must not override compose
docker compose -f deploy/staging/docker-compose.staging.yml \
  --env-file deploy/staging/.env.staging down -v
docker compose -f deploy/staging/docker-compose.staging.yml \
  --env-file deploy/staging/.env.staging up -d --build

# 4) Migrations (explicit Alembic only — no create_all, no auto seed)
./deploy/staging/scripts/migrate.sh

# 5) Optional staging seed (admin + encoding profiles only)
./deploy/staging/scripts/seed_staging.sh

# 6) Ops + smoke
./deploy/staging/scripts/ops_check.sh
./deploy/staging/scripts/smoke_test.sh
```

## Service health (verified)

| Service | Status |
| --- | --- |
| postgres | healthy |
| redis | healthy (requirepass) |
| backend-api | healthy |
| frontend | healthy |
| media-processing-worker | healthy / running |
| publishing-worker | healthy / running |
| nginx | healthy (`0.0.0.0:8080→80`) |

## Migrations

- `alembic upgrade head` via `migrate.sh`
- **current = heads = `010_subscriber_entitlements`**
- No `create_all`; no automatic demo seed
- Staging seed: `python -m scripts.seed_staging` (admin + profiles only)

## DATABASE_URL special characters

- Compose does **not** interpolate an unescaped password into `DATABASE_URL`
- Entrypoint builds URLs with `app.core.db_url.build_postgres_sqlalchemy_url` / `build_redis_url`
- Persists to `/run/ifilm/runtime.env` for healthchecks and `docker exec`
- Staging `POSTGRES_PASSWORD` includes `@ : / #` and is **single-quoted** in `.env.staging` so `#` is not treated as a comment
- Alembic uses `create_engine(database_url)` directly (ConfigParser `%` safe)
- Regression: `tests/test_database_url.py`; ops_check proves live connect with special password
- **Caution:** host `APP_ENV` overrides compose interpolation — staging compose forces `APP_ENV: staging`

## Test video (smoke)

| Property | Value |
| --- | --- |
| Generator | lavfi `testsrc` + `sine` + unique `drawtext` |
| Resolution | 640×360 |
| Duration | 45.00s |
| Codecs | H.264 + AAC |
| Location | `deploy/staging/.tmp-smoke/` (gitignored) |

## Smoke result (verified)

`smoke_test: PASSED` covering admin login → upload → probe → encode → publish → fixture login → entitlement → protected master/variant/segment + Range 206 → watch history / Continue Watching → unpublish deny + history tombstone → anonymous `/media|/packages|/originals` denied.

HLS renditions observed: **240p, 360p**.

## Environment highlights

| Variable | Staging intent |
| --- | --- |
| `APP_ENV` | `staging` (forced in compose) |
| `SUBSCRIBER_IDENTITY_MODE` | `fixture` |
| `STAGING_ALLOW_FIXTURE_AUTH` | `true` |
| `RADIUS_ENTITLEMENT_MAPPING_ENABLED` | `false` |
| Uploads / processing / HLS / local streaming | `true` |
| Live Radius / CDN / R2 / S3 / DRM | **off** |

## Remaining production BLOCKER

Live SAS Radius entitlement attribute mapping is **unverified**. Keep `RADIUS_ENTITLEMENT_MAPPING_ENABLED=false` and do not enable live Radius identity in production.

## Related docs

- [BACKUP_AND_RECOVERY.md](./BACKUP_AND_RECOVERY.md)
- [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md)
- [../audits/STAGING_DEPLOYMENT_AUDIT.md](../audits/STAGING_DEPLOYMENT_AUDIT.md)
