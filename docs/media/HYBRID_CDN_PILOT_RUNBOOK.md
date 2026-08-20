# Hybrid CDN — single-branch pilot runbook (lab → future staging)

**Dependency order:** #81 → #82 → #83 → #84 → #85 → Phase 6 (HTTP candidate)  
**Status:** Documentation only. No live pilot is authorized by this file alone.

## Preconditions

- Phase 1–4 stacked branches reviewed; all CDN flags default **OFF** in compose/installer.
- Capacity plan produced by `plan_branch_cache_capacity` is `safe=true`.
- Phase 5 lab report classification is `lab_ready` (synthetic only).
- Human approval recorded; staging evidence plan agreed.
- Branch node will hold **public keys only** — no private signing keys, Portal/SAS, or customer DB.

## Shadow-first sequence

1. Enable control-plane registry in a **non-production** lab only.
2. Run Phase 4 sim + Phase 5 workload/gates offline.
3. Shadow routing dry-run (Phase 3) — confirm central fallback reasons; **no client redirects**.
4. If ever progressing to staging later: one site/branch identity, fixed allowlisted origin, mTLS at proxy (future), reversible flags.

## Success gates (lab)

- Auth fail rate ≤ threshold
- Fallback rate ≤ threshold
- Cache hit ratio ≥ threshold
- p95 fill latency ≤ threshold
- Disk headroom ≥ threshold
- Partial files = 0
- Central `/api/stream/{token}` behavior unchanged when flags OFF

## Abort gates

- Capacity plan rejected / overflow
- Error budget burned
- Private key or Portal/SAS material detected on branch config
- Any attempt to enable DNS cutover, Cloudflare Stream default delivery, or broad multi-branch rollout

## Rollback

1. Set all hybrid CDN flags false (including Phase 4/5 lab flags).
2. Confirm `client_redirect_active=false` and central playback healthy.
3. Delete **only** the dedicated validated cache root used in lab.
4. Do not run production migrations for cache inventory (none exist in Phase 4/5).

## Explicit non-goals

- No production/VPS deployment from this runbook
- No real enrollment credentials in git or APIs
- No live origin traffic from the Phase 5 tooling
- No claim of `live_pilot_ready` from synthetic results
