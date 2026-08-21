# Hybrid CDN Phase 3 — branch-cache CONTROL PLANE

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase2-origin-delivery-4873` (PR #82)  
**Branch:** `cursor/hybrid-cdn-phase3-cache-control-plane-4873`

## Boundary

**In scope (this phase)**
- Durable `branch_cache_nodes` registry (migration `027_branch_cache_control_plane_v1`)
- Strict node_id / base_url validation (anti-SSRF shape checks; **no** operator-driven fetches)
- Admin-only secret-free management APIs under `/api/admin/branch-cache/*` (`cdn.read` / `cdn.manage`)
- Heartbeat contract: prefer mTLS at trusted proxy later; app path stores **SHA-256 hash** of one-time enrollment tokens only
- Asymmetric short-lived **edge grants** (ES256 JWT): issuer/audience/node/site/package/session/path/TTL/jti/kid; public-key verify
- Deterministic **shadow** routing engine with central-origin fallback reasons
- Observability counters (low cardinality); feature flags default OFF
- Threat model + enrollment/key-rotation / rollback documentation

**Deferred (data-plane / pilot)**
- Live client redirects to branch base URLs
- Pull-through fill, eviction, prewarm, real node enrollment over the network
- mTLS enrollment automation and production key ceremony
- Cloudflare as optional tertiary fallback
- Extending or reviving legacy `cdn_sync` / `/admin/cdn/*`

## Flags (all default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_CONTROL_PLANE` | Registry + admin APIs |
| `ENABLE_EDGE_GRANT_ISSUE` | Allow signing edge grants (requires PEM keys + control plane) |
| `ENABLE_BRANCH_CACHE_SHADOW_ROUTING` | Dry-run routing decisions (no client redirect) |

Compose, installer, and `.env.example` keep these false. Staging/production validation rejects enabling edge grants without control plane or keys, and rejects combining control plane with legacy `ENABLE_CDN_SYNC`.

## Schema

`branch_cache_nodes`: `node_id` (unique), `site_id`, `branch_code` (soft), `base_url`, lifecycle `status`, `draining`, `disabled`, capacity/usage, software/protocol versions, heartbeat/health timestamps, `heartbeat_token_hash` (never returned), optional node public key fields, audit timestamps. **No private signing keys in DB.**

## APIs (admin)

- `GET /status` — flags + counters (secret-free); works even when control plane flag is off
- `GET|POST|PATCH /nodes…`, enrollment-token rotate, heartbeat recorder
- `POST /routing/dry-run` — shadow decision only
- `POST /edge-grants/issue|verify`, `GET /jwks` — public verification material only

Never returns: enrollment hashes, private keys, Portal/SAS, storage credentials, customer data. Enrollment raw token returned **once** on create/rotate.

## Security / threat model

| Trust boundary | Notes |
|----------------|-------|
| Admin RBAC | `cdn.read` / `cdn.manage` (+ legacy `cdn`) |
| Node identity (future) | mTLS at reverse proxy; hashed enrollment only as bootstrap |
| Edge grant verify | Public key / JWKS; alg pinned ES256; reject HS*/none confusion |
| Private keys | Config/env only (`EDGE_GRANT_PRIVATE_KEY_PEM`); never logs/DB/API/frontend |
| URL validation | Reject credentials, query/fragment, loopback, link-local, metadata hosts; no outbound calls in Phase 3 |
| Playback | Central `/api/stream/{token}/…` unchanged when flags OFF; Phase 3 does not redirect |

### Key rotation plan
1. Generate new ES256 key pair offline; set `EDGE_GRANT_KEY_ID` to new kid with new PEMs in secret config.
2. Deploy public key to branch nodes (JWKS) before cutting signing to new kid.
3. Old grants expire within TTL ≤ 300s; no long-lived edge tokens.

### Failure / fallback
Routing selects only enabled, healthy, non-draining, protocol-compatible, capacity-sufficient, heartbeat-fresh nodes for the requested `site_id`. Ordering: free capacity DESC, `node_id` ASC. Otherwise **central origin** with explicit reason codes. Cloudflare is never mandatory.

## Rollback
1. Keep / set all Phase 3 flags false — no registry APIs (except status), no grants, shadow routing unused.
2. Alembic downgrade `027` → `026` only in non-production if needed.
3. Phase 1/2 object-storage and A1 Portal/SAS paths untouched.

## Capacity planning
Use `capacity_bytes` / `used_bytes` and `BRANCH_CACHE_MIN_FREE_BYTES` to keep headroom for ABR ladders. Counters avoid per-subscriber / per-URL cardinality.

## Next phase
Offline data-plane simulation is documented in `HYBRID_CDN_PHASE4.md` (stacked after this control plane).

## Quarantine
Legacy `app/services/cdn_sync.py` and `/admin/cdn/*` remain experimental and unsigned — do not revive for branch delivery.
