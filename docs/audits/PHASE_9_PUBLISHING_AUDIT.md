# Phase 9 — Publishing Workflow Audit

**Date:** 2026-07-31  
**Base:** `main` @ `c3ecf320a3f8793adb1ffeee068653960e2a5908` (Phase 8 squash)  
**Branch:** `media/publishing-workflow`  
**Alembic head before Phase 9:** `007_streaming_service`

---

## Current state model (verbatim)

`CATALOG_STATUSES = ("draft", "published", "archived")` in `app/models/enums.py`.

| Entity | status | published_at | deleted_at | featured/trending |
| --- | --- | --- | --- | --- |
| Movie | yes (default draft) | yes | yes | yes |
| Series | yes (+ `airing_status`) | yes | yes | yes |
| Season | yes | **no** | yes | no |
| Episode | yes | yes | yes | no |

### How status changes today

- `publish_entity()` → `status=published`, sets `published_at` once
- `unpublish_entity()` → `status=draft` (collapses “was live” into draft)
- `soft_delete()` → `deleted_at=now`, `status=archived`
- Admin PATCH can set `status` including `archived` **without** `deleted_at` (HIGH/BLOCKER inconsistency)
- Episode publish requires parent season+series published
- Series/movie publish does **not** require active HLS package
- Series can be published with zero episodes
- Season status is raw setattr; no dedicated publish helpers / no `published_at`

### Public visibility (shared pattern)

Customer list/detail/search filter: `deleted_at IS NULL` AND `status == "published"`.  
Series seasons/episodes endpoints additionally require parent series (and season) published.  
Featured/trending are applied **on top of** published filter (API mode). Mock mode has no status field and shows everything.

### Playback eligibility

Subscribers: linked movie/episode (+ series/season for episodes) must be `status == "published"` and not soft-deleted. Admins always eligible. Active completed HLS package required for session create (409 if missing) — independent of catalog publish.

### Scheduled publishing

**None.** No `scheduled_publish_at`, no catalog scheduler worker.

### Gaps vs Phase 9 targets

| Target | Today |
| --- | --- |
| draft | exists |
| in_review | missing |
| approved | missing |
| scheduled | missing |
| published | exists |
| unpublished | collapsed into draft |
| archived | exists but PATCH bypass of soft-delete |

---

## Decisions for Phase 9 (from audit)

1. Expand statuses to: `draft`, `in_review`, `approved`, `scheduled`, `published`, `unpublished`, `archived`.
2. Migration `008_publishing_workflow` revising `007_streaming_service`.
3. Central `PublishingWorkflowService` owns all transitions (no direct status mutation from routes).
4. Publish requires active completed HLS package for movies/episodes.
5. Series publish requires ≥1 published episode (or readiness fails).
6. Season visibility: season must be `published` **and** parent series `published` (keep chain checks).
7. Scheduled publishing via worker command + due query (UTC), revalidate readiness at execution.
8. One visibility policy used by homepage, search, details, playback eligibility, featured/trending.
9. Publication events table for transition history.
10. RBAC permissions: `catalog.edit`, `catalog.review`, `catalog.approve`, `catalog.publish`, `catalog.archive` (map onto existing admin role permission lists).

## BLOCKER / HIGH (pre-implementation)

- **B1** Three-state model insufficient for review/schedule/unpublished
- **B2** PATCH can set archived without `deleted_at`
- **B3** Unpublish collapses to draft
- **B4** No scheduler
- **H1** Season lacks `published_at` / publish helpers
- **H2** Series unpublish does not cascade children (safe at query time, confusing in admin)
- **H3** Admin UI allows archived via form PATCH
- **H4** Watch button ignores package readiness
- **H5** Mock mode ignores status
