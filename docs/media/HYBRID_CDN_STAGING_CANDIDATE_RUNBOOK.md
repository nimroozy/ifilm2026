# Hybrid CDN — staging-candidate runbook (Phase 8 package)

**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → #87 → Phase 8  
**Status:** Prepares a staging package. Does **not** authorize live activation.

## Preconditions

- Phase 7 lab artifact available; all CDN flags default **OFF** in production compose/installer.
- Enrollment manifest (`ifilm.branch_node.enrollment.v1`) filled with fingerprints only.
- Client cert validity window ≥ 7 days; CA bundle + client cert/key mounts present.
- `evaluate_staging_candidate_gates` classification `staging_candidate_ready` after human approval flag.
- `live_pilot_ready=false`, `client_redirect_active=false`.

## Preflight checklist

1. Fingerprints match mounts (CA, client cert, edge-grant public key).
2. Clock skew ≤ 60s.
3. Dedicated cache root free space ≥ manifest `min_free_bytes`.
4. mTLS preflight to fixed origin (loopback CI or reviewed staging endpoint).
5. Canary/shadow only — no playlist rewrite to branch for customers.

## Evidence bundle (redacted)

Include: gate JSON, cert fingerprints + notAfter, origin host:port (no URLs with tokens), cache watermarks, drain test result.  
Exclude: private keys, cert PEM bodies, grants, Portal/SAS, customer IDs.

## Rollback / drain

1. Start drain (hits only; no new fills).
2. Shutdown; remove only the staging-candidate cache volume if needed.
3. Leave production compose untouched.

## Explicit non-goals

No VPS/DNS/Cloudflare/R2/MinIO/Ceph access from this repository change. No production merge/deploy.
