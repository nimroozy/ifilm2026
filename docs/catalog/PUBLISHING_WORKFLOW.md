# Catalog Publishing Workflow

**Phase:** 9  
**Migration:** `008_publishing_workflow` (revises `007_streaming_service`)

## Lifecycle states

| Status | Meaning |
| --- | --- |
| `draft` | Editable work in progress |
| `in_review` | Submitted for editorial review |
| `approved` | Approved; may publish or schedule |
| `scheduled` | Approved for future UTC publish |
| `published` | Publicly visible (subject to parent chain for episodes/seasons) |
| `unpublished` | Was live; hidden from public catalog |
| `archived` | Soft-deleted / terminal archive |

## Transition matrix

| From | To |
| --- | --- |
| draft | in_review, archived |
| in_review | approved, draft (reject), archived |
| approved | published, scheduled, archived |
| scheduled | published, unpublished (cancel), archived, approved (reschedule path) |
| published | unpublished, archived |
| unpublished | published, scheduled, archived |
| archived | *(terminal)* |

All transitions go through `PublishingWorkflowService` (`app/services/publishing/workflow.py`).  
Admin PATCH/create **must not** mutate `status`.

## Season visibility

Seasons are **structural**. They have workflow status, but public listing requires season **and** parent series to be `published`. There is no independent season homepage section.

Episodes may reach `published` while a parent series is still unpublished (avoids deadlock with “series needs a published episode”). Public episode visibility still requires series + season + episode all `published`.

## Readiness rules

### Movie

- Title, valid unique slug, synopsis, poster, backdrop, release year, ≥1 genre
- Not archived/deleted
- ≥1 linked media asset with **active** completed HLS package, completed renditions, master playlist file present
- No “newest completed package” fallback — only `is_active`

### Episode

- Parent series/season exist and are not archived/deleted
- Title, valid episode number
- Active completed HLS package (same rules as movie)

### Series

- Metadata + artwork (same as movie fields)
- ≥1 episode with status `published` (archived/deleted children do not count)

### Season

- Parent series exists and is not archived
- Valid season number
- No package requirement (structural)

## Package integrity after publish

If the active package later fails integrity:

- Playback eligibility / session create denies play
- Publication status may remain `published`
- Admin readiness shows `playable=false` and issues
- Public catalog may still list the title; Watch/playback fails safely

## Scheduled publishing

- Store `scheduled_publish_at` in UTC
- Admin UI should display in local/admin timezone
- Worker: `python -m app.workers.publishing` (`--once`, `--batch N`, or poll loop)
- Docker Compose service: `publishing-worker`
- At execution: revalidate readiness; on failure leave item `approved`, clear schedule, record `publication_failed`
- Idempotent claim via row locks (`SKIP LOCKED` when available)

## Permissions

| Permission | Actions |
| --- | --- |
| `catalog.read` | readiness, history |
| `catalog.edit` | metadata (also `movies.manage` / `series.manage` for CRUD) |
| `catalog.review` | submit for review |
| `catalog.approve` | approve / reject to draft |
| `catalog.publish` | publish, schedule, unpublish |
| `catalog.archive` | archive |

`movies.manage` / `series.manage` do **not** satisfy workflow publish/approve/review/archive.

## Admin API

```
POST /api/admin/catalog/{entity_type}/{id}/submit-review
POST /api/admin/catalog/{entity_type}/{id}/approve
POST /api/admin/catalog/{entity_type}/{id}/publish
POST /api/admin/catalog/{entity_type}/{id}/schedule
POST /api/admin/catalog/{entity_type}/{id}/unpublish
POST /api/admin/catalog/{entity_type}/{id}/archive
GET  /api/admin/catalog/{entity_type}/{id}/publication-readiness
GET  /api/admin/catalog/{entity_type}/{id}/publication-history
```

`entity_type`: `movie` | `series` | `season` | `episode`

Legacy `/admin/movies|series|episodes/{id}/publish|unpublish` delegate to the workflow (require `catalog.publish`).

## Public visibility

One policy (`app/services/publishing/visibility.py`) used by:

- Homepage list fetches
- Search
- Movie/series details
- Season/episode public lists
- Playback eligibility (subscriber path)
- Featured / trending (never override status)

Unpublished/scheduled/draft/archived content must not leak via slug, id, search, related, or player routes.

Admins preview via admin APIs only.

## Audit history

Table `media_publication_events` records transitions and failures (no secrets/tokens).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| 409 `not_ready` on publish | readiness endpoint issues (package, artwork, genres) |
| Scheduled item never publishes | worker running? `scheduled_publish_at` due? readiness failure events? |
| Published but cannot play | active package integrity / eligibility |
| Series cannot publish | need ≥1 published episode |

## Deferred

Subtitles, watch history, payments, entitlements, CDN/R2/S3, DRM, recommendations, analytics, Phase 10.
