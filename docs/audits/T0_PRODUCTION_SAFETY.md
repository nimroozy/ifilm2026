# T0 Production Safety (PR #66)

**Train:** Platform hardening + security  
**Baseline:** v1.14.2  
**Migrations:** none  
**UI changes:** none  

---

## Changed surface (summary)

| Area | Files |
|------|-------|
| Pipeline docs | `docs/media/PIPELINE.md`, `docs/media/HLS_ENCODING_PIPELINE.md` |
| Legacy gate | `app/backend/app/services/legacy_encoding.py`, upload/encoding routes, ARQ `workers/tasks.py` |
| Lifecycle helper | `app/backend/app/services/media_processing/lifecycle.py` |
| Nginx log redaction | `deploy/staging/nginx/nginx.conf`, `conf.d/ifilm.conf` |
| App log redaction | `app/backend/app/core/logging_filters.py` |
| RBAC demo fixtures | `app/backend/app/services/demo/constants.py`, `docs/security/ADMIN_ROLES.md` |
| Compose workers | `docker-compose.yml`, production + staging compose labels / `ENABLE_ENCODING=false` |
| Secret hygiene | `docs/security/SECRET_HYGIENE.md`, `frontend_env_allowlist.py`, `scan-build-secrets.mjs` |
| Tests / CI | backend RBAC/legacy/secret tests; packaging compose+nginx tests; Frontend/Installer CI steps |

---

## Production impact

- **Playback / HLS multi-audio / subs:** unchanged packaging path (`media-processing-worker`).  
- **Legacy EncodingJob:** cannot run when `APP_ENV` is production/staging (503 / worker refuse).  
- **Nginx:** access logs redact `/api/stream/{token}` → `[REDACTED]`; requires nginx reload on deploy.  
- **Demo roles only:** Catalog/Media/Reviewer/Publisher fixture permissions tightened; production Super Admin merge remains additive.  
- **Admin playback:** requires `streaming.read` for admin JWT on `POST /api/playback/sessions`.

---

## Security impact

- Stream tokens removed from nginx access request line.  
- App logs redact path tokens, secret query params, Bearer, TMDB/api_key-style assignments.  
- Frontend build scanned for secret-shaped `VITE_*` and credential patterns.  
- Legacy encode cannot silently mark jobs complete in prod/staging.

---

## Rollback

1. Redeploy previous digest-pinned release via update-agent.  
2. **No database rollback** (no migrations).  
3. Prefer keeping nginx log redaction even if app digest rolls back.  

---

## Ready gate checklist

- [x] Pipeline documented (transitions / failure / retry / owner)  
- [x] Legacy processing blocked (API + ARQ)  
- [x] Stream tokens protected (nginx + app logs)  
- [x] Logs sanitized  
- [x] RBAC verified (fixture + API tests)  
- [x] Secret scans (allowlist + build scan script + CI)  
- [x] Compose validation (canonical always-on; legacy profile-gated / absent in prod)  
- [x] No migration  
- [x] No UI changes  

**Do not start T1 until this PR is merged and production verified.**
