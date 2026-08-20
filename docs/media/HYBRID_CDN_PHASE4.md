# Hybrid CDN Phase 4 — branch-cache DATA-PLANE simulation

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase3-cache-control-plane-4873` (PR #83)  
**Branch:** `cursor/hybrid-cdn-phase4-cache-dataplane-sim-4873`  
**Dependency order:** #81 → #82 → #83 → Phase 4

## Boundary

**In scope (offline / simulated)**
- Data-plane core that verifies Phase 3 ES256 edge grants with **public keys only** before any cache or origin I/O
- `LocalDirOriginFetcher` deterministic origin adapter (no per-request URLs)
- Dedicated cache-root engine: root confinement, symlink reject, atomic fill (temp+fsync+rename), checksum/size verify, single-flight coalescing, Range/ETag/content-type, LRU eviction with high/low watermarks, drain, pin/in-use protection
- Bounded prewarm planner (dedupe/cancel/limits) — simulation only
- Explicit central-origin fallback decisions without caching bad bytes
- Shadow integration with Phase 3 grants/routing concepts; **no client redirects**
- Pilot readiness harness modeling hit ratio, origin bytes, fill latency, eviction, outage fallback
- Docs + threat model updates

**Deferred**
- Live branch HTTP service / production compose activation
- Real mTLS OriginFetcher (scaffold exists as `DeferredHttpOriginFetcher` — raises on construct)
- Client redirects from central `/api/stream/{token}`
- Real node enrollment, DNS, Cloudflare, MinIO/Ceph/R2 connections
- Durable DB schema for cache inventory (local metadata files suffice)

## Flags (all default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_DATA_PLANE_SIM` | Master switch for offline sim |
| `ENABLE_BRANCH_CACHE_PULL_THROUGH` | Miss → OriginFetcher fill |
| `ENABLE_BRANCH_CACHE_LOCAL_SERVE` | Serve from local cache after grant verify |

Staging/production startup **rejects** enabling the sim (Phase 4 remains lab-only). No private signing key is required or allowed on the data-plane path — public PEM only.

## Authorization

Before cache/origin I/O, `verify_edge_grant` enforces issuer/audience/node/site/package/session/path/kid/TTL/alg pin/replay. Path traversal, encoded tricks, cross-package paths, and requests outside `path_prefix` are rejected.

## Failure / fallback

| Event | Behavior |
|-------|----------|
| Flags OFF | Engine returns disabled/fallback; central playback unchanged |
| Auth failure | 403 decision; no I/O |
| Cache hit | Serve local bytes (Range supported) |
| Miss + pull-through | Single-flight fill; verify size/checksum; atomic commit |
| Origin fail/timeout/checksum | Central fallback; **no** bad bytes cached |
| Drain + miss | Central fallback |
| Eviction | LRU among non-in-use, non-pinned, complete objects only |

## Security / threat model

| Boundary | Notes |
|----------|-------|
| Grant verify | Public key only; never private signing key on branch |
| OriginFetcher | Fixed local root; deferred HTTP forbids redirects/credentials/per-request URLs |
| Cache root | Never delete/read outside configured root; reject symlinks |
| Observability | Bounded counters; no token/session/IP/URL/secret labels |
| Central stream | Untouched; `client_redirect_active` remains false |

## Rollback

1. Keep all Phase 4 flags false (default).
2. Delete lab cache roots under configured sim paths only.
3. No Alembic migration in this phase.

## Pilot readiness

`run_pilot_readiness_report()` exercises cold miss, hit, range, manifest, auth deny, origin outage, and capacity bounds without external systems.
