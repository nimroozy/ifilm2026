# Security Audit — iFilm v1.14.2

**Date:** 2026-08-09  
**Baseline:** production `v1.14.2`  
**Companion:** `COMPLETE_AUDIT.md`, `FIX_PLAN.md`, `PRODUCTION_AUDIT.md`  
**Prior art:** `docs/backend/THREAT_MODEL.md`, `SECURITY.md`

---

## Security score: **7.0 / 10**

Packaged HLS, JWT typing, upload sniffing, RBAC on modern media/publishing routes, CSP, and digest-pinned deploys are strong. Score is held down by edge stream-token logging risk, Option A unprotected CDN URLs, and least-privilege gaps on some admin/legacy routes — not by a wholesale packaged-stream bypass.

---

## Already strong

| Area | Evidence |
| --- | --- |
| Password hashing | Argon2id for admins |
| JWT typing | `typ=admin` vs `typ=subscriber` enforced in deps |
| Subscriber refresh | Rotation + reuse detection / family revoke |
| Playback tokens | Opaque, HMAC-hashed at rest, TTL, revoke APIs, app log redaction |
| Stream paths | Label/segment regexes; packages-only roots; symlink/escape rejection |
| No public media StaticFiles | Removed; nginx must not expose originals/packages |
| Uploads | Filename sanitization, MIME allowlist (incl. audio), content sniff, category allowlist |
| External attach SSRF | HTTPS-only, private IP block, no redirects, acknowledge flag |
| Admin RBAC | Fine-grained perms on media/tracks/publishing/content-requests |
| Content-request IDOR | Subscriber scoped to own rows |
| Secrets | Compose requires JWT/playback secrets; features default off; fixture auth blocked in prod |
| CORS/CSP | Explicit origins; production CSP without `unsafe-eval` |
| Release integrity | Signed manifest, GHCR digests, Trivy/SBOM |

---

## Findings

### HIGH

| ID | Finding | Impact | Location |
| --- | --- | --- | --- |
| S1 | Nginx access logs can capture raw `/api/stream/{token}/…` paths | Token replay until TTL/revoke if logs leak | `deploy/staging/nginx/**` (used by prod compose) |
| S2 | Option A returns unprotected CDN URLs in playback session JSON; revoke does not revoke CDN | Durable URL leak; demo subscribers may play external | `api/routes/stream.py`, eligibility |
| S3 | Any authenticated admin can `POST /playback/sessions` (no `streaming.manage`) | Low-privilege admins mint streams for unpublished assets | `stream.py`, `eligibility.py` |
| S4 | Legacy `encoding` / `cdn` / `upload` admin routes: `CurrentAdmin` only (feature-flagged) | Flag-on = privilege escalation surface | `routes/encoding.py`, `cdn.py`, `upload.py` |

### MEDIUM

| ID | Finding | Impact | Location |
| --- | --- | --- | --- |
| S5 | Device revoke does not invalidate access JWT until expiry | Stolen access token survives device revoke (~60m) | `devices.py`, `deps.py` |
| S6 | Admin login has no rate limit | Brute-force surface | `admin_auth.py` |
| S7 | Login IP from first `X-Forwarded-For` hop; limiter in-process | Spoof / multi-replica bypass | `auth.py`, `rate_limit.py` |
| S8 | Stream delivery does not re-check entitlement on each segment | Suspended users stream until session TTL | `sessions.py`, `delivery.py` |
| S9 | Admin JWT: no refresh/rotation/server revoke | Compromised admin token lives until exp | `admin_auth.py` |
| S10 | External-media DNS allowlist TOCTOU (rebinding residual) | Admin-gated SSRF residual | `media_external.py` |
| S11 | Tokens in SPA `localStorage` | XSS → session theft (mitigated by CSP) | `frontend/src/lib/api.ts` |
| S12 | Update-agent socket historically world-accessible; shared secret required | Local privilege if secret leaks | installer / agent |

### LOW

| ID | Finding | Notes |
| --- | --- | --- |
| S13 | `application/octet-stream` + AVI unknown sniff path | Constrained; keep allowlist tight |
| S14 | Edge Referrer-Policy weaker than app stream headers | Align nginx to `no-referrer` for stream |
| S15 | Dev compose publishes Postgres/Redis ports | Prod keeps internal — OK |

### No BLOCKER (packaged HLS)

Assuming Option A stays demo/admin-only and legacy `ENABLE_ENCODING`/`ENABLE_UPLOADS` stay controlled: no anonymous media mount and no confirmed subscriber IDOR on content requests.

---

## Recommended fixes (priority)

1. **S1** — Redact nginx stream access logs (custom `log_format` or minimal logging under `/api/stream/`).  
2. **S2** — Never return durable CDN URLs in customer session JSON; proxy or short-lived signed redirect; keep non-demo deny.  
3. **S3/S4** — Require `streaming.manage` for admin playback mint; migrate legacy routes to `require_permissions`; keep flags off.  
4. **S5/S8** — Bind access JWT to device session; optional entitlement re-check or shorter playback TTL.  
5. **S6/S7** — Admin login rate limit; trust only proxy-set client IP.  
6. **S9** — Admin token revoke/denylist or shorter admin TTL.  
7. **S10** — Pin outbound IPs after DNS allowlist for external fetch.  
8. **S12** — Tighten update-agent socket permissions.

---

## Auth / authorization matrix (summary)

| Principal | Can do | Must not |
| --- | --- | --- |
| Anonymous | Public catalog, health | Playback, /me/*, admin |
| Subscriber (active + entitlement) | Play published packaged HLS; watchlist/CW/recs/CR | Unpublished; other users’ CR; admin |
| Admin (RBAC) | Scoped by permissions | Cross domain via coarse aliases |
| Update agent | Install signed releases | Run without shared secret |

---

## Upload / file security

- Categories: originals, trailers, subtitles, **audio**, posters, backdrops  
- Worker must share every API write category (mount contract tests)  
- Packages RO on API — preserve  
- Path traversal middleware + streaming path checks — preserve  

---

## Out of scope / accepted risks

- Subscriber identity mode `disabled` in production until Radius mapping verified (operational)  
- Safari AirPlay hardware validation (product, not auth)  
- Application-only rollback (ops process + DB backups)
