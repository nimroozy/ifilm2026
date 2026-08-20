# Hybrid CDN Phase 5 — pilot readiness / capacity / SLO lab

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase4-cache-dataplane-sim-4873` (PR #84)  
**Branch:** `cursor/hybrid-cdn-phase5-pilot-readiness-4873`  
**Dependency order:** #81 → #82 → #83 → #84 → Phase 5

## Boundary

**In scope (offline / lab)**
- Deterministic ABR capacity planner (overflow-safe)
- Offline workload/trace simulator over Phase 4 engine
- Machine-readable pilot **gates** with pass/fail reasons (lab-ready / pilot-candidate only)
- Bounded-cardinality metrics snapshot + Prometheus text helper (**no HTTP endpoint**)
- Offline branch-node health/readiness evaluation (public key only; forbid private keys / Portal/SAS / customer stores)
- Pilot + rollback runbook documentation

**Deferred**
- Live mTLS HTTP origin adapter, HTTP serving process, production compose service
- Live enrollment, DNS cutover, Cloudflare/R2/MinIO/Ceph access, client redirects
- Declaring a live pilot ready from synthetic evidence alone

## Flag

| Flag | Default | Purpose |
|------|---------|---------|
| `ENABLE_BRANCH_CACHE_PILOT_LAB` | `false` | Marks lab tooling as intentionally enabled in development/test only |

Staging/production startup **rejects** enabling this flag.

## Classification rules

| Result | Meaning |
|--------|---------|
| `lab_ready` | Synthetic gates passed |
| `lab_not_ready` | One or more gates failed |
| `live_pilot_ready` | **Always false** in Phase 5 — requires human approval + real staging evidence later |

## Pilot / rollback runbook (summary)

1. **One branch at a time**; shadow/routing dry-run before any serve experiment.
2. Keep all CDN flags **OFF** in production compose/installer.
3. Success gates: auth fail rate, fallback rate, hit ratio, fill latency, disk headroom, central playback preserved.
4. Abort on error-budget burn, origin persistent failure, or capacity plan rejection.
5. Fallback is always **central origin**; no DNS cutover; no broad rollout.
6. Cache cleanup only under a validated dedicated cache root.
7. Rollback = set flags false; delete lab cache root only.

Full operator narrative: `docs/media/HYBRID_CDN_PILOT_RUNBOOK.md`.

## Security

- Branch side: public verification keys only
- Metrics: fixed names; forbid token/session/subscriber/IP/URL/object-key/credential labels
- No Alembic migration; no `/api/stream/{token}` changes; Portal/SAS untouched
