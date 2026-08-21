# iFilm Fix Plan

**Baseline:** v1.14.2 (`d90cbe1`)  
**Status:** Approved execution order — implement by train  
**Companion docs:** [`COMPLETE_AUDIT.md`](./COMPLETE_AUDIT.md) · [`PRODUCTION_AUDIT.md`](./PRODUCTION_AUDIT.md) · [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md)

---

## Approval

Review of PR #65 audit documents accepted.

**Approved principle:** Do **not** start with UI features. Priority is reducing technical debt and creating a stable platform that can survive a **100k+ movie / 20k+ series** catalog.

**Must not break:**

- HLS multi-audio / subtitles / packaging  
- Protected streaming / Option A CDN  
- Watch history / continue watching  
- Recommendations / watchlist / content requests  
- Localization EN/FA/PS  
- Deployment / update-agent / rollback  

**Do not start until T0–T5 are complete:**

- Recommendations V2  
- AI features  
- Smart TV apps  
- Payments / subscriptions (as product trains)

---

## Required before each train / PR

Every implementation PR must include:

- Migration review (no overlapping migrations)  
- Tests  
- Rollback plan  
- Performance comparison (where applicable)  
- Security review  

---

## Approved implementation roadmap

```
T0  Platform hardening + security     CRITICAL   ← start here (no UI)
T1  Database + performance            HIGH
T2  Media CMS                         HIGH
T3  Movie experience                  HIGH
T4  Metadata platform (people)        HIGH
T5  Search (FTS)                      HIGH
T6  Advanced features                 MEDIUM     (only after T0–T5 stable)
```

---

## TRAIN T0 — Platform hardening + security

**Priority:** CRITICAL  
**First PR title:** `chore: harden media pipeline and security baseline`  
**Constraint:** **No UI changes.**

### Goal

Make the foundation safe before adding more features.

### T0.1 — Media pipeline consolidation

| Field | Detail |
|-------|--------|
| **Problem** | Dual media pipelines; unclear source of truth (legacy arq encode vs Redis `media_jobs` HLS packaging). |
| **Impact** | Ops confusion; risk of duplicate/orphan processing; “encode succeeded” without playable HLS. |
| **Solution** | Create `docs/media/PIPELINE.md` defining the single path: Upload → Asset → Probe → Track association → Encode → Package → Publish → Stream. Canonical object states: `uploaded`, `probing`, `ready`, `encoding`, `packaged`, `published`, `failed`. Quarantine/disable duplicate processing paths in production. No UI. |
| **Files** | `docs/media/PIPELINE.md`, worker/queue/pipeline modules, `deploy/docker-compose*.yml`, feature flags |
| **Migration** | Prefer none; optional cleanup only if required |
| **Complexity** | M |

### T0.2 — Streaming security (nginx / logs)

| Field | Detail |
|-------|--------|
| **Problem** | Access logs may contain playback tokens in query strings. |
| **Impact** | Credential leakage via log aggregation / backups. |
| **Solution** | Sanitize stream URLs in nginx access logs (`token` / `expires` stripped). Verify app logs redact secrets. Add security regression tests. |
| **Files** | `deploy/nginx/*`, installer templates, logging filters, tests |
| **Migration** | No |
| **Complexity** | S–M |

### T0.3 — Admin least privilege

| Field | Detail |
|-------|--------|
| **Problem** | Roles (Super Admin, Catalog Manager, Reviewer, Media Manager) may carry unnecessary permissions; admin playback/session paths may be overly broad. |
| **Impact** | Broken access control / IDOR risk for staff accounts. |
| **Solution** | Audit each role; remove unnecessary permissions; tighten admin playback scope; add permission tests. |
| **Files** | RBAC/permission modules, admin routers, authz deps, tests |
| **Migration** | Maybe role-permission seed update (no overlapping migrations) |
| **Complexity** | M |

### T0.4 — Secret hygiene

| Field | Detail |
|-------|--------|
| **Problem** | Risk of tokens in logs, credentials in frontend, secrets in artifacts, prod env leakage. |
| **Impact** | Credential exposure. |
| **Solution** | Verify and lock down: no tokens in logs; no credentials in frontend bundles; no secrets in CI artifacts; no production env leakage. Document checklist; add automated checks where practical. |
| **Files** | Logging, frontend env usage, CI/workflows, docs |
| **Migration** | No |
| **Complexity** | S–M |

---

## TRAIN T1 — Database + performance

**Priority:** HIGH  
**Goal:** Prepare for larger catalog (100k+ movies, 20k+ series) without redesign.

### T1.1 — PostgreSQL optimization

Review indexes, foreign keys, query plans. Add **only necessary** indexes proven by `EXPLAIN`. No speculative index sprawl. Document before/after.

### T1.2 — Fix N+1

Priority endpoints: search, watchlist, continue watching, recommendations, movie detail. Use join/batch loading. Document query counts.

### T1.3 — Real caching strategy

Evaluate Redis cache for homepage, catalog, recommendations, metadata. Replace/augment in-process cache carefully. **Avoid cache leaks between users.**

| Field | Detail |
|-------|--------|
| **Files** | Catalog/watch/recs routers & services, Redis cache layer, Alembic if indexes added |
| **Migration** | Indexes only when justified |
| **Complexity** | L |

---

## TRAIN T2 — Media CMS

**Priority:** HIGH  
**Goal:** Admin can manage professional content.  
**Note:** UI allowed in this train (not before).

### T2.1 — Artwork management

Upload poster, backdrop, logo, thumbnails, gallery. Validation, resize, WebP, checksum, storage lifecycle, replace/delete. Remove URL-only artwork limitation.

### T2.2 — Media diagnostics page

Admin route `/admin/media/diagnostics`: asset, probe, package, tracks, errors, retry, logs.

| Field | Detail |
|-------|--------|
| **Files** | Admin UI, upload/image pipeline, admin media APIs |
| **Migration** | Possibly artwork asset fields |
| **Complexity** | L |

---

## TRAIN T3 — Movie experience

**Priority:** HIGH  
**Goal:** Netflix/Plex-quality movie/series pages. Mobile first.

Hero: backdrop, title, rating, year, duration, genres, play, trailer.  
Sections: overview, audio/subtitles, cast, crew, similar, collections, recommended.

| Field | Detail |
|-------|--------|
| **Files** | Customer detail pages, CSS, detail/aggregate APIs |
| **Migration** | Prefer none |
| **Complexity** | L |

---

## TRAIN T4 — Metadata platform

**Priority:** HIGH  
**Goal:** People / cast system.

Tables: `people`, `movie_people`, `series_people`. Roles: actor, director, writer.  
Customer: `/person/{id}` — biography, photo, known movies/series.

| Field | Detail |
|-------|--------|
| **Migration** | **Yes** (single coherent migration + backfill) |
| **Complexity** | L |

---

## TRAIN T5 — Search

**Priority:** HIGH  
**Goal:** Replace basic search with PostgreSQL FTS.

Search: title, translated title, original title, cast, genres, year.  
Languages: EN, FA, PS.

| Field | Detail |
|-------|--------|
| **Migration** | **Yes** (`tsvector` / GIN as needed) |
| **Complexity** | L |

---

## TRAIN T6 — Advanced features

**Priority:** MEDIUM  
**Only after T0–T5 are stable.**

- Profiles  
- Kids mode  
- Parental control  
- Smart TV preparation  
- Mobile apps  
- Subscriptions  

---

## Traceability (audit IDs → trains)

| Audit ID | Train |
|----------|-------|
| C1 pipeline consolidation | T0.1 |
| C2 nginx token logging | T0.2 |
| C5 admin least privilege | T0.3 |
| Secret / log hygiene | T0.4 |
| C3/C4 N+1, H2 indexes, H10 home, M9 recs | T1 |
| H1 diagnostics, H3/H4 CMS artwork, H12 uploads | T2 |
| H5 movie detail V2, H9 React Query | T3 |
| H6 people system | T4 |
| H7 FTS search | T5 |
| H8 i18n publish workflow | T2/T5 (as needed; not before T0) |
| L1–L4 profiles/TV/apps/payments | T6 |
| H11 CDN signed URLs | Defer; document in T0 security review, implement later if approved |

---

## First implementation PR

**Train:** T0 only  
**Title:** `chore: harden media pipeline and security baseline`  
**Includes:** T0.1–T0.4  
**Excludes:** UI, CMS, detail redesign, people, FTS, profiles, TV, payments, Recommendations V2, AI  

---

## Final rule

The goal is **not** more features.  
The goal is a **platform that can survive a 100k+ catalog**.

---

*End of FIX_PLAN.md — approved roadmap 2026-08-09*
