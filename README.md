# iFilm 2026

Official repository for the iFilm streaming platform.

## Apps

| Path | Description |
| --- | --- |
| [`app/frontend`](./app/frontend) | Customer + admin UI (Vite / React) |
| [`app/backend`](./app/backend) | FastAPI backend (catalog, media pipeline, recommendations) |

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

Schema migrations target **PostgreSQL**. Current Alembic head: `029_cdn_security_hardening_v1`. `alembic upgrade head` is a PostgreSQL operation; the unit-test suite does not use that migration chain.

Uploads, ffprobe, FFmpeg HLS encoding (H.264/AAC ladder on the media-processing worker), protected streaming, and the adaptive customer player are implemented. Those flags default off. See the linked docs before treating any of them as production operations.

## Recommendations

Deterministic recommendations and What-to-Watch. No ML or external AI. Authenticated shelves use watch history, watchlist, and catalog features. Anonymous home uses popular, new-release, and top-rated shelves.

- [docs/recommendations-v1.md](./docs/recommendations-v1.md)

## CDN and storage

Implemented behind flags that default off. Full movies stay on the authorized streaming path.

- Hybrid CDN / object storage and branch-cache phases: [docs/media/HYBRID_CDN_FOUNDATION.md](./docs/media/HYBRID_CDN_FOUNDATION.md)
- Admin CDN management (R2 settings, nodes, prefix routes): [docs/media/CDN_MANAGEMENT_V1.md](./docs/media/CDN_MANAGEMENT_V1.md)
- Optional public artwork and trailer publishing to Cloudflare R2: [docs/media/ARTWORK_CDN_R2.md](./docs/media/ARTWORK_CDN_R2.md)

Legacy `ENABLE_CDN_SYNC` is a separate experimental flag and stays off in production.

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
# DATABASE_URL must be PostgreSQL. Set JWT_SECRET before starting.
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

## Still out of scope

These are not implemented as product features:

- DRM
- Payments and subscriptions
- Cloudflare Stream as the movie playback backend
- Live SAS Radius entitlement verification (fixture/mock login exists; live mode is unverified)

CDN control plane, optional R2 artwork, watch history, recommendations, and the customer player do exist. They are not a production sign-off. See [docs/backend/PRODUCTION_READINESS.md](./docs/backend/PRODUCTION_READINESS.md).

## CI

- Frontend: `.github/workflows/frontend-ci.yml`
- Backend: `.github/workflows/backend-ci.yml` (ruff, mypy, pytest, Postgres migrations, readiness)
