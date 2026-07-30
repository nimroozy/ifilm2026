# Backend threat model (foundation)

## Scope

In-scope for this foundation hardening pass:

- Credential handling and startup configuration
- Admin and subscriber authentication flows
- Upload intake validation
- Feature-flag isolation for unfinished subsystems

Out of scope / unfinished:

- Real media encoding integrity
- CDN trust boundaries in production
- Full SAS Radius deployment hardening

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
- Static `/media` mount has no per-object authorization.
- CDN sync currently trusts configured node endpoints without a mature authenticity model.
