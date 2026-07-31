# Access Entitlements

Narrow entitlement layer for subscriber playback (Phase 11).  
**Does not** include online payments, billing collection, or plan purchase.

> **PRODUCTION SAFETY — READ FIRST**
>
> - **Live SAS Radius authentication is unverified.**
> - **Radius attribute-to-entitlement mapping requires staging validation.**
> - **Production rollout is blocked until staging verification is complete.**
> - Live Radius entitlement mapping defaults to **disabled**.
> - **Access-Accept alone must never grant playback.**
> - Playback requires a separately validated entitlement result.
> - Unknown, missing, malformed, or unverified Radius entitlement attributes **fail closed**.

## Result shape

```json
{
  "allowed": true,
  "account_status": "active",
  "service_status": "active",
  "package_name": "Premium 50Mbps",
  "branch_code": "Kabul",
  "valid_from": null,
  "valid_until": "2026-12-31T00:00:00+00:00",
  "denial_code": null,
  "safe_reason": null,
  "max_devices": 3,
  "source": "fixture",
  "checked_at": "...",
  "from_cache": false
}
```

## Sources

1. `SubscriberIdentityProvider.get_entitlement(...)` (authoritative when available)
2. Local snapshot cache (`subscriber_entitlement_snapshots`) when still valid
3. Local subscriber fields only when there is no external subject (never invent allow)

## Fail-closed policy

| Condition | Playback |
| --- | --- |
| Access-Accept without validated entitlement attrs | Deny |
| Entitlement mapping disabled | Deny |
| Provider unavailable, no valid allowed cache | Deny |
| Cache expired | Deny (`entitlement_cache_expired`) |
| Account suspended / disabled | Deny |
| Service expired / inactive | Deny |
| Package missing / `unknown` | Deny |
| Malformed expiry | Deny |
| `ENTITLEMENT_CACHE_GRACE_SECONDS` | Default `0` — no offline grace |

Existing playback sessions: opaque HLS tokens remain until expiry/revoke; **new** sessions fail closed when entitlement cannot be confirmed.

## Playback requirements (subscriber)

Must all pass:

1. Authenticated subscriber JWT
2. Active account + active service entitlement (separately validated — not Access-Accept alone)
3. Entitlement not expired
4. Content published and visible (Phase 9)
5. Active completed HLS package
6. Device/session limits satisfied at login/device registration

### Admin operational bypass

Active admins retain operational playback for verification. This is **not** subscriber entitlement and must not be mixed with package/branch authorization.

## Account / service statuses

| Status | Effect |
| --- | --- |
| `active` | Eligible if package/service valid |
| `suspended` | Tokens may exist for profile; playback denied |
| `disabled` | Login denied; APIs rejected |
| `expired` (service) | Playback denied |

Branch/package strings are **display + entitlement snapshot fields**, not client-controlled authorization.

## Watch history integration

- History requires authenticated subscriber identity
- Suspension blocks new playback; history remains private to the subscriber
- Device revocation does not mutate another device’s history rows
- Logout clears frontend tokens/refresh state

## Security

- No client-controlled package/branch authorization
- No entitlement spoofing via request body
- No stale expired cache authorization
- No raw provider errors to clients
- Fixture provider forbidden in production

## Deferred

Online payments, billing collection, plan purchasing, automatic renewal, Cloudflare/CDN/R2/S3, DRM, recommendations, analytics, subtitles, offline downloads, TV apps.
