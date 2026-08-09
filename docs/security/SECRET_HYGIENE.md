# Secret hygiene checklist (T0)

**Baseline:** v1.14.2+  
**Goal:** No playback tokens, JWT secrets, or production credentials in logs, frontend bundles, or CI artifacts.

---

## Rules

1. **Playback tokens** appear only in API response bodies for session create (once). They must never appear in:
   - Application logs (path redaction via `TokenRedactionFilter`)
   - Nginx access logs (`$loggable_uri` / sanitized request line)
   - Error tracker breadcrumbs that include full URLs
2. **JWT / playback HMAC secrets** live only in server env (`JWT_SECRET`, `PLAYBACK_TOKEN_SECRET`) — never `VITE_*`.
3. **Frontend** may expose only public config. Prefer `VITE_PUBLIC_*` for new keys. Current allowlist (`app/backend/app/frontend_env_allowlist.py` + `app/frontend/src/vite-env.d.ts`): `VITE_API_BASE_URL`, `VITE_DATA_MODE`, branding, version, etc.  
   **Forbidden in the SPA bundle:** TMDB tokens, JWT secrets, DB/Redis credentials, storage keys, playback secrets.
4. **CI artifacts** must not upload `.env`, `runtime.env`, admin credential dumps, or raw stream URLs with tokens.
5. **Production env** is not copied into tickets, PR descriptions, or browser QA recordings with live tokens.

---

## Automated coverage

| Check | Location |
|-------|----------|
| Path token redaction | `app/core/logging_filters.py` + `tests/test_streaming_service.py` / `tests/test_secret_hygiene.py` |
| Query param redaction (`token`, `expires`, …) | same filter |
| Nginx sanitized access log | `deploy/staging/nginx/nginx.conf` + `packaging/tests/test_nginx_log_redaction.py` |
| Frontend env surface | `tests` / packaging assertion that `VITE_*` allowlist has no secret names |
| Frontend build scan | `app/frontend/scripts/scan-build-secrets.mjs` (Frontend CI after `pnpm build`) |
| Legacy encoding blocked in prod/staging | `tests/test_legacy_encoding_gate.py` |
| Compose legacy worker gate | `packaging/tests/test_compose_worker_profiles.py` |

---

## Manual release checklist

- [ ] No `PLAYBACK_TOKEN_SECRET` / `JWT_SECRET` / DB passwords in commit diff  
- [ ] Nginx reload after log_format change; rotate access logs if prior tokenful lines exist  
- [ ] Browser QA artifacts scrubbed of `Authorization` headers and `/api/stream/<token>/` URLs  
- [ ] Update-agent / installer env files mode `0600` on host  

---

*End of SECRET_HYGIENE.md*
