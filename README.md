# iFilm 2026

Official repository for the iFilm streaming platform.

## Apps

| Path | Description |
| --- | --- |
| [`app/frontend`](./app/frontend) | Customer + admin UI (Vite / React) |
| [`app/backend`](./app/backend) | FastAPI backend foundation (not production-ready) |

## Security and readiness

- [SECURITY.md](./SECURITY.md)
- [docs/backend/PRODUCTION_READINESS.md](./docs/backend/PRODUCTION_READINESS.md)
- [docs/backend/THREAT_MODEL.md](./docs/backend/THREAT_MODEL.md)

## Quick start

### Backend

```bash
cd app/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Set DATABASE_URL and JWT_SECRET before starting.
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Optional demo seed (development/test only):

```bash
# ADMIN_BOOTSTRAP_PASSWORD must be set explicitly and must not be a known default.
python -m scripts.seed_dev
```

### Frontend

```bash
cd app/frontend
cp .env.example .env
pnpm install
pnpm dev
```

The Vite dev server proxies `/api` to `BACKEND_PORT` (default `8000`).

## CI

- Frontend: `.github/workflows/frontend-ci.yml`
- Backend: `.github/workflows/backend-ci.yml` (ruff, mypy, pytest, Postgres migrations, readiness)
