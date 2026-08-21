# Hybrid CDN / object-storage foundation (Phase 1)

**Status:** Foundation only — feature flags default **OFF**  
**Baseline:** latest `main` after v1.18.1  
**Related:** `PIPELINE.md`, `STREAMING_SERVICE.md`, `docs/backend/THREAT_MODEL.md`

## Target architecture

| Role | Responsibility | Phase |
|------|----------------|-------|
| **Central origin** (S3-compatible: MinIO / Ceph RGW) | Durable source of truth for masters + encoded HLS packages | 1 config + interface; cutover later |
| **Local workspace** (`MEDIA_ROOT`) | Upload/encode scratch; current production path | Existing |
| **Optional hot tier** (Cloudflare R2) | Policy-selected hot/new titles only — **never** full library | 1 config; promote/demote automation later |
| **Branch pull-through caches** | Disposable HLS caches on ISP backbone; verify playback with public keys only | 2+ |
| **Cloudflare CDN / Stream** | Optional website assets, images, trailers, emergency fallback — **not** default full-movie delivery | 2+ |
| **PostgreSQL** | Metadata / control plane only — no Portal/SAS/subscriber secrets in object storage | Unchanged |
| **A1 Portal / SAS + playback sessions** | Authorization remains session-based, short-lived, no permanent public movie URLs | Unchanged |

```
Upload → Probe → Encode → Package (local workspace)
                              ↓ (future)
                     Central origin put (immutable keys)
                              ↓
              Branch cache miss → origin → optional hot tier / CF fallback
                              ↓
              Playback session token → rewrite playlists → segments
```

## Phase 1 boundary (this PR)

**Implemented**
- Provider-neutral `ObjectStorage` protocol
- `local` filesystem provider (default)
- `s3_compatible` provider for MinIO/Ceph/S3 (and R2 via separate role)
- Versioned object-key conventions (`ifilm/v1/...`)
- Explicit storage roles in config (`local_workspace`, `central_origin`, `hot_cdn`, future `branch_cache`)
- Feature flags default off: `ENABLE_OBJECT_STORAGE`, `ENABLE_R2_HOT_TIER`
- Startup validation when flags are on; legacy `ENABLE_CDN_SYNC` rejected in staging/prod
- Secret-free `safe_storage_status()` for diagnostics
- Cost model + later-phase plan (below)
- Quarantine note on experimental `cdn_sync.py` (do not extend)

**Explicitly not in Phase 1**
- Wiring encode/publish/stream to remote origin
- Branch cache agents, registry, prewarm, eviction
- Creating cloud buckets, tokens, DNS, or VPS changes
- Schema migrations
- Enabling flags in production defaults
- Cloudflare Stream as default delivery
- Destructive lifecycle automation against production objects

## Why this boundary

Current production media is **local FS only**. Experimental `cdn_sync` is an unsigned HTTP stub and must not become the hybrid foundation. The smallest coherent unlock is a **provider-neutral origin interface + config/validation/docs** that later phases can attach after package promote—without rewriting upload, encode, or A1 playback.

## Object key conventions (immutable / versioned)

Prefix default: `MEDIA_OBJECT_KEY_PREFIX=ifilm`

| Kind | Key pattern |
|------|-------------|
| Original | `{prefix}/v1/originals/{asset_id}/{stored_filename}` |
| HLS package root | `{prefix}/v1/packages/{asset_id}/{package_id}` |
| Package object | `{prefix}/v1/packages/{asset_id}/{package_id}/{relative_path}` |
| Poster / backdrop / trailer | `{prefix}/v1/{posters\|backdrops\|trailers}/{asset_id}/{filename}` |
| Audio / subtitle sidecars | `{prefix}/v1/{audio\|subtitles}/{asset_id}/{filename}` |

Package IDs remain immutable; a re-encode creates a new `package_id` tree rather than overwriting.

## Configuration (defaults off)

See `app/backend/.env.example`. Critical flags:

| Variable | Default | Meaning |
|----------|---------|---------|
| `ENABLE_OBJECT_STORAGE` | `false` | Master switch for remote origin factory |
| `MEDIA_ORIGIN_PROVIDER` | `local` | `local` \| `s3_compatible` |
| `ENABLE_R2_HOT_TIER` | `false` | Optional hot tier (requires object storage) |
| `CDN_HOT_TIER_MAX_TITLES` | `0` | Must be `>0` if R2 enabled — hard cap |
| `ENABLE_CDN_SYNC` | `false` | Legacy stub — keep off |

Credentials never appear in API responses, frontend bundles, logs, or `safe_storage_status()`.

## Cost model (planning)

Assumptions for planning (replace with measured rates):

| Tier | What lives there | Cost drivers | Guidance |
|------|------------------|--------------|----------|
| **Haroon Net central** (MinIO/Ceph) | Full originals + all HLS packages | Disk/SSD, power, ops | Primary durable store; size for catalog × ABR ladder |
| **Branch cache** | Hot manifests/segments only | Edge SSD, backbone bandwidth | Cap per branch; miss → origin; disposable |
| **Optional R2 hot** | Subset of hot/new titles | Storage + Class A/B ops | Cap via `CDN_HOT_TIER_MAX_TITLES`; cooldown demotes |
| **Cloudflare CDN** | Site assets, posters, trailers, emergency media | Egress / requests | Not full-movie default; Stream not default |

**Do not** mirror the full library to R2 by default. **Do not** use Cloudflare Stream as the default full-movie path.

### Lifecycle concepts (policy only in Phase 1)

1. **Promote** to hot tier when a title is new or exceeds `CDN_HOT_TIER_PROMOTE_VIEWS_THRESHOLD` and capacity remains under `CDN_HOT_TIER_MAX_TITLES`.
2. **Cooldown** after `CDN_HOT_TIER_COOLDOWN_DAYS` without qualifying traffic → mark demotable.
3. **Demote/delete from hot tier only** — central origin remains source of truth. No Phase 1 automation deletes production objects.

## Security invariants

- No permanent public movie URLs; playback stays session-authorized and short-lived.
- Branch caches (future) validate with **verification-only public keys** — never Portal credentials, customer passwords, or a shared origin master secret.
- PostgreSQL holds metadata/control plane; object storage holds media bytes only.
- A1 Portal/SAS architecture unchanged.
- Legacy `cdn_sync` trusts unsigned node URLs — residual risk until replaced.

## Later phases

## Phase 2 — Origin cutover (optional flags)

See also stacked PR docs in this file's Later phases section.

| Flag | Default | Behavior |
|------|---------|----------|
| `ENABLE_ORIGIN_PACKAGE_SYNC` | `false` | After local HLS promote/activate, enqueue idempotent `origin_sync` job |
| `ENABLE_ORIGIN_HLS_READ_FALLBACK` | `false` | On local miss, serve playlist/segment bytes from origin after session auth |

Both require `ENABLE_OBJECT_STORAGE=true`. Local package remains source of truth for publishing readiness; sync failure never un-activates playback.

### Phase 2 — Origin cutover
- Post-promote upload of package trees to central origin (**implemented behind flags**)
- Playback delivery can fetch from origin while keeping token gate (**optional read fallback**)
- Dual-run local + origin with size verification

### Phase 3 — Branch cache control plane
- **Implemented (flags OFF):** durable node registry, admin APIs, ES256 edge-grant primitives, shadow routing + central fallback — see `HYBRID_CDN_PHASE3.md`
- **Deferred:** pull-through fill/eviction/prewarm, live redirects, real enrollment/mTLS, Cloudflare tertiary fallback

### Phase 4 — Branch cache data-plane simulation
- **Implemented (flags OFF):** offline grant-gated cache engine, local OriginFetcher, atomic fill/single-flight, LRU capacity, prewarm planner, pilot readiness harness — see `HYBRID_CDN_PHASE4.md`
- **Deferred:** live branch HTTP service, real mTLS origin adapter, client redirects, production compose activation

### Phase 5 — Pilot readiness / capacity / SLO lab
- **Implemented (flags OFF):** capacity planner, workload simulator, pilot gates, metrics export helper, node health checks, runbook — see `HYBRID_CDN_PHASE5.md` and `HYBRID_CDN_PILOT_RUNBOOK.md`
- **Deferred:** live pilot authorization, staging cutover, DNS, multi-branch rollout

### Phase 6 — Branch HTTP service candidate
- **Implemented (flags OFF):** isolated ASGI factory for lab/TestClient only — see `HYBRID_CDN_PHASE6.md`
- **Deferred (partially addressed in Phase 7):** live mTLS, enrollment, client redirects; container activation remains lab-only

### Phase 7 — Hardened CI/lab branch-node artifact
- **Implemented (flags OFF):** `Dockerfile.branch-cache.lab`, validate-only entry, separate lab compose (`network_mode: none`), hardening contract tests — see `HYBRID_CDN_PHASE7.md`
- **Deferred:** production/staging activation, release digest publication, live networking, enrollment, client redirects, live pilot

### Phase 8 — mTLS staging-candidate package
- **Implemented (flags OFF):** strict mTLS origin fetcher, fixed-origin allowlist, enrollment manifest, staging gates, loopback PKI harness, separate staging-candidate compose — see `HYBRID_CDN_PHASE8.md` and `HYBRID_CDN_STAGING_CANDIDATE_RUNBOOK.md`
- **Deferred:** live staging/production activation, VPS/DNS/cloud access, operator credential issuance, client redirects, live pilot

### Phase 9 — Staging evaluation / pilot evidence (future)
- Hit/miss, origin bandwidth, cache fill latency, error budgets
- Capacity planning worksheets from measured ABR bitrates
- Single-branch pilot rollout runbook; rollback to origin-only

## Operator notes

- Do not enable `ENABLE_OBJECT_STORAGE` or `ENABLE_R2_HOT_TIER` in production until staging cutover is verified.
- Do not enable `ENABLE_CDN_SYNC`.
- No cloud resources or credentials are created by this repository change.
