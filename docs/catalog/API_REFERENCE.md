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
`q`, `genre`, `year`, `language`, `featured`, `trending`, `page`, `page_size`

`sort`: `newest`, `oldest`, `title_asc`, `title_desc`, `rating_desc`, `recently_updated`

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
`movies.read`, `movies.manage`, `series.read`, `series.manage`, `genres.read`, `genres.manage`  
Legacy keys `movies` / `series` from the foundation seed still grant access.
