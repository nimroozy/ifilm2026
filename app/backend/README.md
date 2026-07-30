# iFilm Backend

FastAPI foundation for the iFilm streaming platform.

## Capabilities

- REST API under `/api`
- PostgreSQL schema (SQLAlchemy + Alembic)
- Admin JWT authentication and RBAC roles
- Movies / series / episode management
- Subscriber login via SAS / FreeRADIUS bridge (mock or live)
- Upload intake + encoding job pipeline (inline + ARQ workers)
- HLS playlist packaging / delivery
- CDN node sync jobs

## Quick start (local)

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# For Postgres + Redis:
# docker compose up -d postgres redis

# SQLite-friendly smoke run (override DB):
export DATABASE_URL=sqlite:///./ifilm.db
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

## Docker Compose

From the repository root:

```bash
docker compose up --build
```

Services: `postgres`, `redis`, `api` (:8000), `worker` (ARQ).

## Default credentials

| Role | Username | Password |
| --- | --- | --- |
| Admin | `admin` | `admin123` |
| Subscriber (mock Radius) | `mobin_user_001` | `password` |

## Key endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/config` | Runtime config for frontend |
| POST | `/api/auth/login` | Subscriber login (Radius-backed) |
| GET | `/api/auth/me` | Current subscriber |
| POST | `/api/admin/auth/login` | Admin login |
| GET/POST/PATCH/DELETE | `/api/movies`, `/api/admin/movies` | Catalog + admin CRUD |
| GET/POST/PATCH/DELETE | `/api/series`, `/api/admin/series` | Series + episodes |
| POST | `/api/admin/uploads` + `/file` | Upload + encode |
| GET | `/api/admin/encoding/jobs` | Encoding queue |
| GET | `/api/stream/{type}/{id}` | HLS manifest metadata |
| GET | `/media/hls/...` | HLS files |
| POST | `/api/admin/cdn/sync` | Push content to CDN nodes |

## Workers

```bash
arq app.workers.tasks.WorkerSettings
```

Tasks: `finalize_upload_job`, `process_encoding_job`, `process_cdn_sync_job`.

Encoding currently writes placeholder HLS packages so the delivery path works without ffmpeg. Replace `app/services/encoding.py` / worker body with real ffmpeg ladder generation later.

## SAS Radius

Configured via:

- `RADIUS_ENABLED`
- `RADIUS_MODE=mock|live`
- `RADIUS_SERVER`, `RADIUS_PORT`, `RADIUS_SECRET`, `RADIUS_NAS_IDENTIFIER`

Mock mode authenticates the demo Mobin Net account and soft-accepts other username/password pairs for local development.

## Migrations

```bash
alembic upgrade head
```

On API startup, `create_all` + bootstrap seed also run for foundation/dev convenience.

## Tests

```bash
cd app/backend
pytest -q
```
