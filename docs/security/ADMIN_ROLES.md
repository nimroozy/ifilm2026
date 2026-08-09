# Admin role permission matrix (T0)

**Baseline:** v1.14.2+  
**Principle:** Least privilege. Catalog editors do not run the media pipeline; media operators do not publish; reviewers preview but do not manage sessions globally.

Demo seed roles live in `app/services/demo/constants.py` (`ADMIN_FIXTURES`). Production Super Admin permissions are merged additively from `app/bootstrap.py` (`SUPER_PERMISSIONS`).

---

## Roles

| Role | Purpose |
|------|---------|
| **Super Admin** | Full operational control (all `SUPER_PERMISSIONS`) |
| **Catalog Manager** | Titles, genres, collections, content requests — **not** upload/encode/stream manage |
| **Media Manager** | Upload, probe, encode, package ops, streaming read/manage |
| **Reviewer** | Read catalog + review/approve workflow; streaming **read** for preview; no upload/manage |
| **Publisher** | Publish/archive; streaming **read** only (no global session manage) |

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
