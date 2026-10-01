# iFilm Backend

FastAPI foundation for the iFilm streaming platform.

**This backend is not production-ready.** See [docs/backend/PRODUCTION_READINESS.md](../../docs/backend/PRODUCTION_READINESS.md) and [SECURITY.md](../../SECURITY.md).

## What is implemented

- REST API under `/api`
- **PostgreSQL** schema via **Alembic only** (no `create_all` on startup). Current head: `029_cdn_security_hardening_v1`. Unit tests do not run this migration chain.
- Admin JWT authentication and subscriber authentication
- Movies, series, seasons, episodes, and the publishing workflow
- Watch history, Continue Watching, and watchlist
- Deterministic recommendations and What-to-Watch ([docs/recommendations-v1.md](../../docs/recommendations-v1.md))
- Resumable uploads, ffprobe, and FFmpeg HLS encoding (`encode_hls` on `python -m app.workers.media_processing`) when `ENABLE_MEDIA_PROCESSING` and `ENABLE_HLS_ENCODING` are enabled
- Protected local streaming when `ENABLE_LOCAL_STREAMING` is enabled
- Hybrid CDN control plane, admin CDN management, and optional Cloudflare R2 artwork/trailer publishing (flags default off)

## What is unfinished

- Advanced flags default **off**. Enabling them is not a production sign-off.
- Legacy `ENABLE_ENCODING` does not write HLS packages. Real packages come from the media-processing worker. The placeholder HLS writer has been removed.
- Legacy `ENABLE_CDN_SYNC` stays off in production. It is separate from hybrid CDN and CDN management.
- SAS Radius **live** mode is unverified.
- Upload, streaming, and CDN node provisioning still need production operational sign-off. See [docs/backend/PRODUCTION_READINESS.md](../../docs/backend/PRODUCTION_READINESS.md).

## Quick start (local development)

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# DATABASE_URL must be PostgreSQL. Set JWT_SECRET and (for seeding) ADMIN_BOOTSTRAP_PASSWORD.
# Do not use example/default secrets in staging or production.

alembic upgrade head
python -m scripts.seed_dev   # explicit demo seed only; never runs on API startup
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs  
Readiness: http://127.0.0.1:8000/ready

## Docker Compose

From the repository root, export required secrets first:

```bash
export POSTGRES_PASSWORD='...'
export JWT_SECRET='...'   # e.g. openssl rand -hex 32
docker compose config      # validate
docker compose up --build
```

Compose does not print or hard-code admin passwords. Seed separately if needed.

## Feature flags (default OFF)

| Flag | Default | Purpose |
| --- | --- | --- |
| `ENABLE_UPLOADS` | `false` | Resumable upload intake |
| `ENABLE_MEDIA_PROCESSING` | `false` | ffprobe jobs and the processing worker |
| `ENABLE_HLS_ENCODING` | `false` | FFmpeg HLS encode jobs (also requires media processing) |
| `ENABLE_LOCAL_STREAMING` | `false` | Protected `/api/stream/{token}` playback |
| `ENABLE_ENCODING` | `false` | Legacy encoding-job flag. Does not write HLS packages |
| `ENABLE_CDN_SYNC` | `false` | Legacy experimental sync. Keep off in production |
| `ENABLE_OBJECT_STORAGE` | `false` | S3-compatible origin provider |
| `ENABLE_R2_HOT_TIER` | `false` | Optional Cloudflare R2 hot tier |
| `ENABLE_ARTWORK_CDN_SYNC` | `false` | Public artwork/trailer publishing to R2 |
| `ENABLE_RADIUS_LOGIN` | `false` | Subscriber Radius login |

## Mock Radius rules

- Allowed only when `APP_ENV` is `development` or `test`
- Authenticates only users listed in `RADIUS_MOCK_USERS`
- Rejected at startup for staging/production

## Commands

```bash
ruff check app scripts tests
mypy app scripts
pytest -q
alembic upgrade head
python -m scripts.seed_dev
```
