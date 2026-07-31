# iFilm Backend

FastAPI foundation for the iFilm streaming platform.

**This backend is not production-ready.** See [docs/backend/PRODUCTION_READINESS.md](../../docs/backend/PRODUCTION_READINESS.md) and [SECURITY.md](../../SECURITY.md).

## What is implemented

- REST API under `/api`
- PostgreSQL schema via **Alembic only** (no `create_all` on startup)
- Admin JWT authentication
- Movies / series / episode management APIs
- Feature-flagged experimental paths for upload, placeholder encoding, CDN sync, and Radius login

## What is unfinished / experimental

- Encoding output is **placeholder HLS packaging**, not real ffmpeg encoding
- CDN sync is **experimental**
- SAS Radius **live** mode is **unverified**
- Upload and streaming paths are **not production-ready**

## Quick start (local development)

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Set DATABASE_URL, JWT_SECRET, and (for seeding) ADMIN_BOOTSTRAP_PASSWORD in .env
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
| `ENABLE_UPLOADS` | `false` | Upload intake |
| `ENABLE_ENCODING` | `false` | Placeholder encoding jobs |
| `ENABLE_CDN_SYNC` | `false` | Experimental CDN sync |
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
