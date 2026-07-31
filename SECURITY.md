# Security Policy

## Reporting issues

Report suspected security issues privately to the repository maintainers. Do not open public issues that include secrets, credentials, or exploit details.

## Hard requirements

- Never commit real JWT secrets, database passwords, Radius secrets, or admin passwords.
- `ADMIN_BOOTSTRAP_PASSWORD` has no unsafe default and is required only for the explicit seed command.
- Staging/production startup refuses unsafe defaults for:
  - `JWT_SECRET`
  - `DATABASE_URL` credentials
  - `RADIUS_SECRET`
  - `ADMIN_BOOTSTRAP_PASSWORD` (when set)
- `RADIUS_MODE=mock` is allowed only when `APP_ENV` is `development` or `test`.
- Mock Radius authenticates only users listed in `RADIUS_MOCK_USERS`.
- Advanced features default to disabled:
  - `ENABLE_UPLOADS=false`
  - `ENABLE_ENCODING=false`
  - `ENABLE_CDN_SYNC=false`
  - `ENABLE_RADIUS_LOGIN=false`
  - `ENABLE_MEDIA_PROCESSING=false`
  - `ENABLE_HLS_ENCODING=false`
  - `ENABLE_LOCAL_STREAMING=false`
- When `ENABLE_LOCAL_STREAMING=true`, `PLAYBACK_TOKEN_SECRET` must be set (≥32 chars, no unsafe defaults).
- The full `MEDIA_ROOT` is **not** publicly mounted. HLS packages are only served via protected `/api/stream/{token}/…` routes. Optional artwork uses a separate `ARTWORK_ROOT` at `/artwork`.
- Playback tokens must never appear in logs, admin list responses, or metrics (paths are redacted).

## Authentication notes

- Admin authentication uses local password hashes and JWT access tokens.
- Subscriber login through SAS/FreeRADIUS is experimental when `RADIUS_MODE=live`.
- Invalid login responses use a generic error message and must not leak account state.

## Data and media

- Schema changes must go through Alembic migrations.
- Upload, encoding, HLS delivery, and CDN sync paths are not production-ready.
- Do not expose `/media` directly on the public internet without an access-control layer.
