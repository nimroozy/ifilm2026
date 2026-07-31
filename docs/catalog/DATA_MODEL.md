# Catalog data model

## Entities

### Movie
`id`, `title`, `original_title`, `slug` (unique), `description`, `short_description`, `release_year`, `release_date`, `duration_minutes`, `age_rating`, `language`, `country`, `imdb_id` (unique when set), `imdb_rating`, `poster_url`, `backdrop_url`, `trailer_url`, `status`, `is_featured`, `is_trending`, `published_at`, `created_at`, `updated_at`, `deleted_at`

Compatibility fields kept for streaming stubs: `director`, `cast`, `audio`, `subtitles`, `qualities`, `dubbed`, `views`, `hls_path`, `source_path`.

### Series
Same core metadata as movies, plus `end_year`, `airing_status` (display lifecycle such as Ongoing/Completed), and relationships to seasons/genres.

### Season
`id`, `series_id`, `season_number` (unique per series), `title`, `description`, `poster_url`, `release_year`, `status`, timestamps, `deleted_at`.

### Episode
`id`, `season_id`, `series_id`, `episode_number` (unique per season), `title`, `description`, `duration_minutes`, `release_date`, `thumbnail_url`, `status`, `published_at`, timestamps, `deleted_at`, plus `hls_path`/`source_path` for deferred playback work.

### Genre
`id`, `name`, `slug` (unique), `description`, timestamps.

### Relationships
- `movie_genres` many-to-many
- `series_genres` many-to-many
- Series → Seasons → Episodes

## Migration

- `001_initial` / `002_movies_title_idx` unchanged
- `003_catalog_admin` adds genres/seasons/M2M and expands movie/series/episode columns with data backfill
