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
- [ ] Alembic upgrade on empty PostgreSQL
- [ ] Alembic upgrade from previous revision
- [ ] `/ready` succeeds against Postgres + Redis
- [ ] Production settings reject unsafe defaults
