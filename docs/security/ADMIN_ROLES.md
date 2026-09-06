# Admin role permission matrix (T0)

**Baseline:** v1.14.2+  
**Principle:** Least privilege. Catalog editors do not run the media pipeline; media operators do not publish; reviewers preview but do not manage sessions globally.

Demo seed roles live in `app/services/demo/constants.py` (`ADMIN_FIXTURES`). Production Super Admin permissions are merged additively from `app/bootstrap.py` (`SUPER_PERMISSIONS`).

---

## Roles

| Role | Purpose |
|------|---------|
| **Super Admin** | Full operational control (all `SUPER_PERMISSIONS`) |
| **Catalog Manager** | Catalog metadata only (titles, genres, collections, content requests) — **not** media upload/edit/delete/processing |
| **Media Manager** | Media upload, edit (tracks), delete, processing — **not** users/settings/publish |
| **Reviewer** | Review / approve only; streaming **read** for preview; no media edit |
| **Publisher** | Publish / archive only; streaming **read**; no media delete |


---

## Permission matrix (high level)

| Capability | Super Admin | Catalog Manager | Media Manager | Reviewer | Publisher |
|------------|:-----------:|:---------------:|:-------------:|:--------:|:---------:|
| `catalog.read` / movies/series/genres/collections read | ✓ | ✓ | ✓ (read) | ✓ | ✓ |
| `catalog.edit` / `*.manage` catalog | ✓ | ✓ | — | — | — |
| `catalog.review` / `catalog.approve` | ✓ | — | — | ✓ | — |
| `catalog.publish` / `catalog.archive` | ✓ | — | — | — | ✓ |
| `content_requests.*` | ✓ | ✓ | — | read | — |
| `upload.*` / `processing.*` | ✓ | — | ✓ | read (processing) | read (processing) |
| `streaming.read` (preview) | ✓ | — | ✓ | ✓ | ✓ |
| `streaming.manage` (admin sessions / revoke-all) | ✓ | — | ✓ | — | — |
| `system_updates.*` | ✓ | — | — | — | — |
| `cdn.read` / `cdn.manage` / `cdn.provision` / `cdn.routing` / `cdn.secrets` (Admin → CDN, Storage / R2) | ✓ | — | — | — | — |

Legacy aliases (`movies`, `upload`, `streaming`, …) still satisfy dotted permissions via `PERMISSION_ALIASES`.

**Important:** the bare permission `streaming` aliases to **`streaming.manage`**. Demo Reviewer/Publisher fixtures therefore use only `streaming.read` (never bare `streaming`) so they can preview without global session administration.

---

## Playback access

- **Subscribers:** entitlement + published + active package (unchanged).  
- **Admins** calling `POST /api/playback/sessions` must hold `streaming.read` (or manage/legacy `streaming`).  
- **Admin session APIs** (`/api/admin/playback/sessions*`) require `streaming.manage` for create/revoke-all; list requires `streaming.read`.

---

## Tests

See `app/backend/tests/test_admin_role_permissions.py`.

---

*End of ADMIN_ROLES.md*
