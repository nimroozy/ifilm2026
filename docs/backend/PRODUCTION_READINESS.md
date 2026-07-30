# Backend production readiness

Status: **not production-ready**.

This document tracks unfinished or experimental backend systems so they are not mistaken for complete features.

## Safe to rely on (foundation only)

- FastAPI process bootstrap with environment validation
- Alembic-managed PostgreSQL schema
- Admin JWT login against locally stored admin users
- Movies/series CRUD API shapes
- Generic auth failure responses
- Feature flags defaulting advanced systems to off

## Not production-ready

| Area | Current state | Required before production |
| --- | --- | --- |
| Encoding | Placeholder HLS package writer only; no real ffmpeg ladder | Real encoding workers, checksums, retries, observability |
| HLS delivery | Serves generated placeholder playlists/segments | Authenticated playback URLs, packaging QA, CDN origin hardening |
| CDN sync | Experimental HTTP/no-op sync | Signed sync protocol, conflict handling, monitoring |
| SAS Radius live mode | Unverified client path | Validated against SAS/FreeRADIUS in staging, timeout/retry policy |
| Uploads | Feature-flagged local file intake | Virus scanning, multipart resume, object storage, authZ audits |
| Streaming path | Manifest endpoint + static media mount | Tokenized URLs, bandwidth controls, audit logs |
| Auto-seed on startup | Removed | Use explicit `python -m scripts.seed_dev` in non-prod only |

## Required deployment controls

1. Set strong unique values for `JWT_SECRET`, database credentials, and `RADIUS_SECRET`.
2. Keep `APP_ENV=production` (or `staging`) and `DEBUG=false`.
3. Run `alembic upgrade head` before starting API processes.
4. Keep `ENABLE_UPLOADS`, `ENABLE_ENCODING`, `ENABLE_CDN_SYNC`, and `ENABLE_RADIUS_LOGIN` disabled until each subsystem is verified.
5. Do not run the development seed command in production.

## Verification checklist

- [ ] Backend lint (`ruff`)
- [ ] Backend typecheck (`mypy`)
- [ ] Backend pytest suite
- [x] Alembic upgrade on empty PostgreSQL (Docker smoke, 2026-07-30)
- [ ] Alembic upgrade from previous revision
- [x] `/api/health/ready` succeeds against Postgres + Redis (Docker smoke, 2026-07-30)
- [ ] Production settings reject unsafe defaults

## Docker Compose end-to-end smoke test (2026-07-30)

**Result: PASS** on branch `backend/foundation` (PR #2), after worker startup fixes.

### Commands

```bash
# Temporary local secrets (not committed; chmod 600)
# POSTGRES_PASSWORD=$(openssl rand -hex 24)
# JWT_SECRET=$(openssl rand -hex 32)
# ADMIN_BOOTSTRAP_PASSWORD=<strong temporary password for explicit seed only>

export POSTGRES_PASSWORD JWT_SECRET
export ENABLE_UPLOADS=false ENABLE_ENCODING=false ENABLE_CDN_SYNC=false ENABLE_RADIUS_LOGIN=false

docker compose down -v
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 docker compose up --build -d

docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current

curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health/live
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health/ready
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs

docker compose exec -T -e ADMIN_BOOTSTRAP_PASSWORD api python -m scripts.seed_dev
# then admin login / me checks against /api/admin/auth/*

docker compose ps
docker compose logs --no-color --tail=200
docker compose down -v
```

### Service health

| Service | Status |
| --- | --- |
| postgres | healthy |
| redis | healthy |
| api | up (running) |
| worker | up (no crash loop) |

### HTTP status codes

| Endpoint | Status | Notes |
| --- | --- | --- |
| `GET /api/health` | **200** | `{"status":"ok",...}` |
| `GET /api/health/live` | **200** | `{"status":"live"}` |
| `GET /api/health/ready` | **200** | database ok, redis ok |
| `GET /docs` | **200** | OpenAPI UI |
| `POST /api/admin/auth/login` (seeded admin) | **200** | access token issued |
| `POST /api/admin/auth/login` (invalid password) | **401** | `{"detail":"Invalid credentials"}` |
| `GET /api/admin/auth/me` (no token) | **401** | `{"detail":"Not authenticated"}` |
| `GET /api/admin/auth/me` (valid token) | **200** | username `admin` |

### Migrations / defaults

- Alembic reached `002_movies_title_idx (head)` on an empty volume.
- No automatic admin seed on API startup (`ADMIN_BOOTSTRAP_PASSWORD` unset in API container; admin created only via explicit `python -m scripts.seed_dev`).
- Feature flags remained disabled: `ENABLE_UPLOADS`, `ENABLE_ENCODING`, `ENABLE_CDN_SYNC`, `ENABLE_RADIUS_LOGIN` all `false`; `RADIUS_ENABLED` `false`.
- No unsafe default credentials were created by the stack.

### Log audit

- No passwords, JWT secrets, database credentials, or Radius secrets observed in `docker compose logs --tail=200`.
- No repeated exceptions after the clean recreate with the worker fix.
- Worker started once and remained up (no crash loop).

### Environment notes / remaining risks

- This smoke host required `net.bridge.bridge-nf-call-iptables=0` for reliable container-to-container bridge traffic (Docker/nftables interaction in the agent VM). Treat as an environment caveat, not an application default.
- Compose was built with classic builder (`DOCKER_BUILDKIT=0`) because BuildKit/overlay was unavailable in the agent environment.
- Advanced media/CDN/Radius paths remain **not production-ready**; keep flags off until each subsystem is verified.
- Status remains **not production-ready** overall.
