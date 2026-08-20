# Backend threat model (foundation)

## Scope

In-scope for this foundation hardening pass:

- Credential handling and startup configuration
- Admin and subscriber authentication flows
- Upload intake validation
- Feature-flag isolation for unfinished subsystems

Out of scope / unfinished:

- Full CDN trust boundaries for branch pull-through caches (Phase 2+)
- Full SAS Radius deployment hardening

Hybrid object-storage Phase 1 adds a provider-neutral origin interface with flags
default OFF. See `docs/media/HYBRID_CDN_FOUNDATION.md`.

## Assets

- Admin credentials and JWT signing key
- Subscriber/ISP identity assertions
- Catalog metadata
- Uploaded media files and HLS outputs
- Database and Redis availability

## Adversaries

- External unauthenticated clients
- Authenticated subscribers attempting admin actions
- Misconfigured deployments using example secrets
- Path traversal / oversize upload abuse

## Key threats and mitigations

| Threat | Mitigation in this PR |
| --- | --- |
| Default credentials in staging/prod | Startup validation rejects known unsafe JWT/DB/Radius/admin defaults |
| Mock auth in production | `RADIUS_MODE=mock` refused outside development/test |
| Credential stuffing feedback | Generic `Invalid credentials` responses |
| Privilege escalation via subscriber JWT | Admin dependencies require `typ=admin` |
| Expired token reuse | JWT `exp` enforced; expired tokens rejected |
| Upload path traversal | Filename sanitizer rejects `..`, separators, unsafe characters |
| Upload content spoofing | Content-type allow-list enforcement |
| Oversized uploads | `UPLOAD_MAX_BYTES` enforced on create and stream |
| Accidental unfinished feature exposure | Feature flags default to disabled |

## Residual risks

- Live Radius integration is unverified.
- Placeholder encoding can be mistaken for real HLS output if flags are enabled prematurely.
- Static `/media` mount has no per-object authorization (removed from public serving; do not reintroduce).
- Legacy CDN sync (`ENABLE_CDN_SYNC`) trusts configured node endpoints without a mature authenticity model — keep disabled; do not build hybrid CDN on it.
- Object-storage credentials, when configured, must never be exposed via APIs, frontend, or logs (`safe_storage_status` is secret-free).
- Optional R2 hot tier must remain capacity-capped; mirroring the full library defeats cost and security goals.
