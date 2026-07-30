# iFilm 2026

Official repository for the iFilm streaming platform.

## Apps

| Path | Description |
| --- | --- |
| [`app/frontend`](./app/frontend) | Customer + admin UI (Vite / React) |
| [`app/backend`](./app/backend) | FastAPI backend, workers, Postgres schema |

## Quick start

### Backend

```bash
cd app/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
export DATABASE_URL=sqlite:///./ifilm.db
uvicorn app.main:app --reload --port 8000
```

Or with Docker: `docker compose up --build`

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
- Backend: `.github/workflows/backend-ci.yml`
