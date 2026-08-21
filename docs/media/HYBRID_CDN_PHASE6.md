# Hybrid CDN Phase 6 — branch HTTP service candidate (offline / test only)

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase5-pilot-readiness-4873` (PR #85)  
**Branch:** `cursor/hybrid-cdn-phase6-branch-service-candidate-4873`  
**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → Phase 7

## Boundary

**In scope**
- Isolated ASGI app factory `create_branch_cache_app()` — **not** mounted in the central app
- Immutable object `GET`/`HEAD` at `/v1/obj/{asset}/{package}/{path}` via Phase 4 engine
- Public ES256 grant verification before any cache/origin I/O
- Injected local origin transport; deferred HTTPS adapter (no live sockets)
- Optional lab `/health`, `/ready`, `/metrics` (disabled by default)
- Drain/shutdown state, bounded fills, single-flight (engine), safe errors, request-id, log redaction
- Startup validation forbidding private signing keys, Portal/SAS, broad roots, prod activation

**Deferred**
- Real mTLS sockets, production/staging compose activation, enrollment, client redirects, live pilot
- (Container lab artifact moved to Phase 7 — still not production-activated)

## Flags (all default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_HTTP_SERVICE` | Master switch (rejected in staging/production) |
| `ENABLE_BRANCH_CACHE_HTTP_HEALTH` | Expose `/health`+`/ready` when constructing lab app |
| `ENABLE_BRANCH_CACHE_HTTP_METRICS` | Expose `/metrics` when constructing lab app |
| `ENABLE_BRANCH_CACHE_HTTP_LAB_HTTPS_ADAPTER` | Allow constructing deferred HTTPS adapter (still needs injected transport) |

## Service contract

- Auth: `Authorization: Bearer <edge_grant>` + `X-Ifilm-Session-Id`
- Grant `path_prefix` must be `/v1/obj/{asset_id}/{package_id}/`
- Range / ETag / content-type preserved from engine
- Fallback: HTTP 503 + `X-Ifilm-Fallback: central_origin` (no client redirect)
- No directory listing, no OpenAPI, no debug tracebacks

## Threat model (delta)

| Risk | Mitigation |
|------|------------|
| Grant leakage in logs | Bearer + grant query redaction |
| SSRF via origin URL | No per-request URLs; injected local transport only |
| Prod activation | Startup + settings validation reject prod-like envs |
| Symlink/traversal | Engine + path normalization + reject encoded tricks |
| Secret material on branch | Config forbids private keys / Portal/SAS / customer DB |

## Rollback

Keep flags false. Do not add the service to compose. Central `/api/stream/{token}` unchanged.
