# iFilm 2026

Official repository for the iFilm streaming platform.

## Apps

| Path | Description |
| --- | --- |
| [`app/frontend`](./app/frontend) | Customer + admin UI (Vite / React) |
| [`app/backend`](./app/backend) | FastAPI backend (catalog + local media pipeline) |

## Catalog administration

Authorized admins can manage movies, series, seasons, episodes, genres, artwork URLs, featured/trending flags, and the controlled publishing workflow (draft → review → approve → publish/schedule).

Docs:

- [docs/catalog/ARCHITECTURE.md](./docs/catalog/ARCHITECTURE.md)
- [docs/catalog/DATA_MODEL.md](./docs/catalog/DATA_MODEL.md)
- [docs/catalog/API_REFERENCE.md](./docs/catalog/API_REFERENCE.md)
- [docs/catalog/ADMIN_WORKFLOWS.md](./docs/catalog/ADMIN_WORKFLOWS.md)
- [docs/catalog/PUBLISHING_WORKFLOW.md](./docs/catalog/PUBLISHING_WORKFLOW.md)
- [docs/catalog/FRONTEND_INTEGRATION.md](./docs/catalog/FRONTEND_INTEGRATION.md)
- [docs/catalog/TEST_REPORT.md](./docs/catalog/TEST_REPORT.md)

## Watch history

Authenticated subscribers get persistent progress, Resume/Start Over, Continue Watching, and Watch History.

- [docs/user/WATCH_HISTORY.md](./docs/user/WATCH_HISTORY.md)

Frontend data mode:

- `VITE_DATA_MODE=mock` (default) — local fixtures
- `VITE_DATA_MODE=api` — real FastAPI catalog (no silent mock fallback)

## Media pipeline (local)

| Phase | Flag(s) | Docs |
| --- | --- | --- |
| Resumable upload | `ENABLE_UPLOADS` | [docs/media/UPLOAD_FOUNDATION.md](./docs/media/UPLOAD_FOUNDATION.md) |
| Probe (ffprobe) | `ENABLE_MEDIA_PROCESSING` | [docs/media/MEDIA_PROCESSING_FOUNDATION.md](./docs/media/MEDIA_PROCESSING_FOUNDATION.md) |
| HLS encoding | `ENABLE_MEDIA_PROCESSING` + `ENABLE_HLS_ENCODING` | [docs/media/HLS_ENCODING_PIPELINE.md](./docs/media/HLS_ENCODING_PIPELINE.md) |
| Protected streaming | `ENABLE_LOCAL_STREAMING` | [docs/media/STREAMING_SERVICE.md](./docs/media/STREAMING_SERVICE.md) |
| Adaptive customer player | (uses streaming) | [docs/media/VIDEO_PLAYER.md](./docs/media/VIDEO_PLAYER.md) |

**Important:** The full `MEDIA_ROOT` is **not** publicly mounted. Anonymous `/media/**` access was removed. HLS packages are delivered only via protected `/api/stream/{token}/…` routes. Optional artwork may be served from `ARTWORK_ROOT` at `/artwork`.

Alembic head: `007_streaming_service`.

Uploads, ffprobe processing, local HLS encoding, protected streaming, and the adaptive customer HLS video player are implemented. Persistent watch history, CDN, DRM, and payments remain deferred.

## Security and readiness

- [SECURITY.md](./SECURITY.md)
- [docs/backend/PRODUCTION_READINESS.md](./docs/backend/PRODUCTION_READINESS.md)
- [docs/backend/THREAT_MODEL.md](./docs/backend/THREAT_MODEL.md)
- [docs/audits/PHASE_7_REPOSITORY_AUDIT.md](./docs/audits/PHASE_7_REPOSITORY_AUDIT.md)

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

Cloudflare Stream / CDN / R2 / S3, DRM, live SAS Radius entitlement rules, customer player integration, binary artwork upload productization, watch-history sync, recommendations, payments/subscriptions, and production deployment hardening remain out of scope for the current local media phases.

## CI

- Frontend: `.github/workflows/frontend-ci.yml`
- Backend: `.github/workflows/backend-ci.yml` (ruff, mypy, pytest, Postgres migrations, readiness)
