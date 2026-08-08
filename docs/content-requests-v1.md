# Content Requests V1 (Request Movie)

Authenticated subscribers can request movies or series that are not yet in the
iFilm catalog. Admins review requests, optionally link fulfilled titles, and see
aggregate demand. Submitting a request never guarantees acquisition.

## Migration

- Revision: `021_content_requests_v1`
- Tables: `content_requests`, `content_request_events`

## Subscriber API

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/me/content-requests` | Create (or return existing / already-available / suggestions) |
| GET | `/api/me/content-requests` | List own requests |
| GET | `/api/me/content-requests/{id}` | Own request detail |
| DELETE | `/api/me/content-requests/{id}` | Withdraw → `withdrawn` (only `new` / `reviewing`) |

Strict subscriber isolation (IDOR-safe). Public responses never include `admin_note`.

## Admin API

Requires dedicated RBAC (not granted by collection-only roles):

| Permission | Capability |
|------------|------------|
| `content_requests.read` | List/detail/aggregates |
| `content_requests.manage` | Status transitions + catalog link |

| Method | Path |
|--------|------|
| GET | `/api/admin/content-requests` |
| GET | `/api/admin/content-requests/aggregates` |
| GET | `/api/admin/content-requests/{id}` |
| POST | `/api/admin/content-requests/{id}/actions` |

Actions: `review`, `approve`, `reject`, `mark_added`, `reopen`.

Demo roles: Catalog Manager gets read+manage; Reviewer gets read only.
Super Admin merges both via bootstrap.

## Status workflow

```
NEW → REVIEWING → APPROVED → ADDED
NEW/REVIEWING → REJECTED
NEW/REVIEWING → WITHDRAWN (subscriber)
REJECTED → REVIEWING (admin reopen only)
```

Rejected cannot jump to Added without reopen.

## Duplicate rules

Catalog (exact → block create):

1. TMDB ID
2. IMDb ID
3. Normalized title + year
4. Title-only as fuzzy suggestion (user may `force`)

Per-user open/rejected request duplicate (TMDB / IMDb / title+year) → return existing.

## Rate limits

- Max 5 new requests / subscriber / 24h (`CONTENT_REQUEST_MAX_PER_DAY`)
- Max 20 open (`new`/`reviewing`/`approved`) requests (`CONTENT_REQUEST_MAX_OPEN`)
- Clear `429` with codes `rate_limited` / `too_many_open_requests`

## Out of scope (V1)

Automated download/acquisition, torrent/piracy integrations, AI approval,
new notification systems, feeding recommendations from request activity.
