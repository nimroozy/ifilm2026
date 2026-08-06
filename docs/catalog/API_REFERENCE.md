# Catalog API reference

All list endpoints use:

```json
{ "data": [], "meta": { "page": 1, "page_size": 20, "total": 0, "pages": 0 } }
```

## Public

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/movies` | Published only; filters below |
| GET | `/api/movies/{id_or_slug}` | Published only |
| GET | `/api/series` | Published only |
| GET | `/api/series/{id_or_slug}` | Published only |
| GET | `/api/series/{id_or_slug}/seasons` | Published series seasons |
| GET | `/api/seasons/{id}/episodes` | Published episodes |
| GET | `/api/genres` | Genre list |
| GET | `/api/search` | Published movies + series by query |

### Filters / sort
`q`, `genre`, `year`, `language`, `featured`, `trending`, `has_dubbed`, `has_subtitles`, `page`, `page_size`

`sort`: `newest`, `oldest`, `title_asc`, `title_desc`, `rating_desc`, `recently_updated`

### Availability fields (movie / series / episode)
Backward-compatible additions — see `docs/catalog/AUDIO_SUBTITLE_AVAILABILITY.md`:

- `audio_availability`: `original_language`, `languages`, `dubbed_languages`, `track_count`, `source`, `selectable_in_player`
- `subtitle_availability`: `languages`, `track_count`, `source`, `selectable_in_player`

Legacy `audio` / `subtitles` / `dubbed` string arrays remain.

## Admin (Bearer admin JWT + RBAC)

### Movies
`GET/POST /api/admin/movies`, `GET/PATCH/DELETE /api/admin/movies/{id}`, `POST .../publish`, `POST .../unpublish`

### Series
`GET/POST /api/admin/series`, `GET/PATCH/DELETE /api/admin/series/{id}`, `POST .../publish`, `POST .../unpublish`

### Seasons
`GET/POST /api/admin/series/{series_id}/seasons`, `GET/PATCH/DELETE /api/admin/seasons/{id}`

### Episodes
`GET/POST /api/admin/seasons/{season_id}/episodes`, `GET/PATCH/DELETE /api/admin/episodes/{id}`, publish/unpublish

### Genres
`GET/POST /api/admin/genres`, `PATCH/DELETE /api/admin/genres/{id}`  
Delete returns **409** while assigned to non-deleted movies/series.

### Dashboard
`GET /api/admin/dashboard/stats` — catalog counts only (no invented analytics)

## Permissions

Fine-grained keys: `movies.read`, `movies.manage`, `series.read`, `series.manage`,
`genres.read`, `genres.manage`.

Legacy coarse keys from the foundation seed (exact alias map):

| Required | Satisfied by |
| --- | --- |
| `movies.read` | `movies.read`, `movies.manage`, `movies` |
| `movies.manage` | `movies.manage`, `movies` |
| `series.read` | `series.read`, `series.manage`, `series` |
| `series.manage` | `series.manage`, `series` |
| `genres.read` | `genres.read`, `genres.manage`, `genres` |
| `genres.manage` | `genres.manage`, `genres` |

`movies` / `series` do **not** grant genre management. `movies.read` cannot mutate movies.
