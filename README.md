# iFilm 2026

Official repository for the iFilm streaming platform.

## Apps

| Path | Description |
| --- | --- |
| [`app/frontend`](./app/frontend) | Customer + admin UI (Vite / React) |
| [`app/backend`](./app/backend) | FastAPI backend (catalog admin foundation; not production-ready media) |

## Catalog administration

Authorized admins can manage movies, series, seasons, episodes, genres, artwork URLs, publishing status, and featured/trending flags.

Docs:

- [docs/catalog/ARCHITECTURE.md](./docs/catalog/ARCHITECTURE.md)
- [docs/catalog/DATA_MODEL.md](./docs/catalog/DATA_MODEL.md)
- [docs/catalog/API_REFERENCE.md](./docs/catalog/API_REFERENCE.md)
- [docs/catalog/ADMIN_WORKFLOWS.md](./docs/catalog/ADMIN_WORKFLOWS.md)
- [docs/catalog/FRONTEND_INTEGRATION.md](./docs/catalog/FRONTEND_INTEGRATION.md)
- [docs/catalog/TEST_REPORT.md](./docs/catalog/TEST_REPORT.md)

Frontend data mode:

- `VITE_DATA_MODE=mock` (default) — local fixtures
- `VITE_DATA_MODE=api` — real FastAPI catalog (no silent mock fallback)

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

## Explicitly deferred

Real FFmpeg encoding, ABR ladders, subtitles/DRM, signed streaming URLs, live SAS Radius, CDN replication, binary artwork uploads, watch-history sync, recommendations, payments/subscriptions, and production deployment are out of scope for this milestone.

## CI

- Frontend: `.github/workflows/frontend-ci.yml`
- Backend: `.github/workflows/backend-ci.yml` (ruff, mypy, pytest, Postgres migrations, readiness)
