"""catalog administration schema

Revision ID: 003_catalog_admin
Revises: 002_movies_title_idx
Create Date: 2026-07-30

Slug backfill notes (PostgreSQL):
- Titles are normalized with lower() + regexp_replace to [a-z0-9] tokens.
- Empty / Unicode-only titles (e.g. Dari/Persian with no Latin letters) become
  base slug ``item``, then disambiguated with ``-<id>`` on collisions.
- Collisions are detected on the 280-char bare prefix so long titles that share
  the same truncated prefix are disambiguated together.
- Collision rows reserve ``length('-' || id)`` before truncating the base, then
  append ``-<id>`` so the deterministic suffix is never clipped by the 280 limit.
- The lowest-id row in a collision group keeps the bare (truncated) slug.
- Multiple NULL imdb_id values remain allowed.
- Duplicate non-null imdb_id values abort the migration with an actionable error
  (no silent deletion). Legacy 002 schema has no imdb_id column, so values are
  NULL unless manually populated mid-upgrade; the guard still runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_catalog_admin"
down_revision = "002_movies_title_idx"
branch_labels = None
depends_on = None


def _backfill_unique_slugs(table: str) -> None:
    """Assign non-empty unique slugs using pure PostgreSQL (no app Python)."""
    op.execute(
        sa.text(
            f"""
            WITH normalized AS (
              SELECT
                id,
                NULLIF(
                  trim(both '-' FROM regexp_replace(
                    lower(COALESCE(NULLIF(btrim(title), ''), 'item')),
                    '[^a-z0-9]+',
                    '-',
                    'g'
                  )),
                  ''
                ) AS base_raw
              FROM {table}
            ),
            prepared AS (
              SELECT id, COALESCE(base_raw, 'item') AS base
              FROM normalized
            ),
            candidates AS (
              SELECT
                id,
                base,
                left(base, 280) AS bare_slug
              FROM prepared
            ),
            ranked AS (
              SELECT
                id,
                base,
                bare_slug,
                COUNT(*) OVER (PARTITION BY bare_slug) AS cnt,
                MIN(id) OVER (PARTITION BY bare_slug) AS min_id
              FROM candidates
            )
            UPDATE {table} AS t
            SET slug = CASE
              WHEN r.cnt = 1 OR t.id = r.min_id THEN r.bare_slug
              ELSE left(
                     r.base,
                     GREATEST(0, 280 - length('-' || t.id::text))
                   ) || '-' || t.id::text
            END
            FROM ranked AS r
            WHERE t.id = r.id
            """
        )
    )
    # Final safety: never leave empty/null slugs.
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET slug = 'item-' || id::text
            WHERE slug IS NULL OR btrim(slug) = ''
            """
        )
    )


def _assert_no_duplicate_imdb(table: str) -> None:
    # table name is an internal constant (movies|series), not user input
    op.execute(
        sa.text(
            f"""
            DO $guard$
            DECLARE
              dup_id text;
              dup_count integer;
            BEGIN
              SELECT imdb_id, COUNT(*)::integer
                INTO dup_id, dup_count
              FROM {table}
              WHERE imdb_id IS NOT NULL AND btrim(imdb_id) <> ''
              GROUP BY imdb_id
              HAVING COUNT(*) > 1
              ORDER BY COUNT(*) DESC
              LIMIT 1;

              IF dup_id IS NOT NULL THEN
                RAISE EXCEPTION
                  'Cannot migrate {table}: duplicate non-null imdb_id "%" already exists on % row(s). '
                  'Deduplicate or null conflicting imdb_id values, then re-run alembic upgrade.',
                  dup_id,
                  dup_count
                  USING ERRCODE = 'unique_violation';
              END IF;
            END
            $guard$
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "genres",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_genres_slug"),
    )
    op.create_index("ix_genres_slug", "genres", ["slug"], unique=False)

    op.create_table(
        "movie_genres",
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id", sa.Integer(), sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "series_genres",
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id", sa.Integer(), sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- movies: add new columns ---
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("slug", sa.String(length=280), nullable=True))
        batch.add_column(sa.Column("short_description", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("release_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("imdb_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("imdb_rating", sa.Float(), nullable=True))
        batch.add_column(sa.Column("poster_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("backdrop_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("trailer_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("is_featured", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("is_trending", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE movies SET
          release_year = year,
          duration_minutes = duration,
          imdb_rating = rating,
          poster_url = poster,
          backdrop_url = backdrop,
          status = CASE WHEN published THEN 'published' ELSE 'draft' END,
          is_featured = featured,
          is_trending = false,
          short_description = '',
          trailer_url = '',
          published_at = CASE WHEN published THEN created_at ELSE NULL END
        """
    )

    _backfill_unique_slugs("movies")
    _assert_no_duplicate_imdb("movies")

    with op.batch_alter_table("movies") as batch:
        batch.alter_column("slug", existing_type=sa.String(length=280), nullable=False)
        batch.alter_column("status", existing_type=sa.String(length=32), nullable=False, server_default="draft")
        batch.create_unique_constraint("uq_movies_slug", ["slug"])
        batch.create_unique_constraint("uq_movies_imdb_id", ["imdb_id"])
        batch.create_index("ix_movies_slug", ["slug"], unique=False)
        batch.create_index("ix_movies_status", ["status"], unique=False)
        batch.create_index("ix_movies_release_year", ["release_year"], unique=False)
        batch.create_index("ix_movies_language", ["language"], unique=False)
        batch.create_index("ix_movies_is_featured", ["is_featured"], unique=False)
        batch.create_index("ix_movies_is_trending", ["is_trending"], unique=False)
        batch.create_index("ix_movies_deleted_at", ["deleted_at"], unique=False)
        batch.drop_column("year")
        batch.drop_column("duration")
        batch.drop_column("rating")
        batch.drop_column("genres")
        batch.drop_column("poster")
        batch.drop_column("backdrop")
        batch.drop_column("featured")
        batch.drop_column("published")

    # --- series ---
    with op.batch_alter_table("series") as batch:
        batch.add_column(sa.Column("slug", sa.String(length=280), nullable=True))
        batch.add_column(sa.Column("short_description", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("end_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("imdb_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("imdb_rating", sa.Float(), nullable=True))
        batch.add_column(sa.Column("poster_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("backdrop_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("trailer_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("catalog_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("airing_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("is_featured", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("is_trending", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE series SET
          release_year = year,
          imdb_rating = rating,
          poster_url = poster,
          backdrop_url = backdrop,
          catalog_status = CASE WHEN published THEN 'published' ELSE 'draft' END,
          airing_status = COALESCE(status, 'Ongoing'),
          is_featured = false,
          is_trending = false,
          short_description = '',
          trailer_url = '',
          published_at = CASE WHEN published THEN created_at ELSE NULL END
        """
    )

    _backfill_unique_slugs("series")
    _assert_no_duplicate_imdb("series")

    with op.batch_alter_table("series") as batch:
        batch.drop_column("status")
        batch.alter_column("catalog_status", new_column_name="status", existing_type=sa.String(length=32), nullable=False)
        batch.alter_column("slug", existing_type=sa.String(length=280), nullable=False)
        batch.create_unique_constraint("uq_series_slug", ["slug"])
        batch.create_unique_constraint("uq_series_imdb_id", ["imdb_id"])
        batch.create_index("ix_series_slug", ["slug"], unique=False)
        batch.create_index("ix_series_status", ["status"], unique=False)
        batch.create_index("ix_series_release_year", ["release_year"], unique=False)
        batch.create_index("ix_series_language", ["language"], unique=False)
        batch.create_index("ix_series_is_featured", ["is_featured"], unique=False)
        batch.create_index("ix_series_is_trending", ["is_trending"], unique=False)
        batch.create_index("ix_series_deleted_at", ["deleted_at"], unique=False)
        batch.drop_column("year")
        batch.drop_column("rating")
        batch.drop_column("genres")
        batch.drop_column("seasons")
        batch.drop_column("episode_count")
        batch.drop_column("poster")
        batch.drop_column("backdrop")
        batch.drop_column("published")

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.String(length=1024), nullable=True),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("series_id", "season_number", name="uq_season_number_per_series"),
    )
    op.create_index("ix_seasons_series_id", "seasons", ["series_id"], unique=False)
    op.create_index("ix_seasons_status", "seasons", ["status"], unique=False)
    op.create_index("ix_seasons_deleted_at", "seasons", ["deleted_at"], unique=False)

    op.execute(
        """
        INSERT INTO seasons (series_id, season_number, title, status, created_at, updated_at)
        SELECT DISTINCT e.series_id, e.season, 'Season ' || e.season,
               CASE WHEN s.published_at IS NOT NULL THEN 'published' ELSE 'draft' END,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM episodes e
        JOIN series s ON s.id = e.series_id
        """
    )

    with op.batch_alter_table("episodes") as batch:
        batch.add_column(sa.Column("season_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("episode_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("release_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("thumbnail_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE episodes SET
          season_id = (
            SELECT s.id FROM seasons s
            WHERE s.series_id = episodes.series_id AND s.season_number = episodes.season
            LIMIT 1
          ),
          episode_number = episode,
          duration_minutes = duration,
          thumbnail_url = thumbnail,
          status = CASE WHEN published THEN 'published' ELSE 'draft' END,
          published_at = CASE WHEN published THEN created_at ELSE NULL END,
          updated_at = created_at
        """
    )

    with op.batch_alter_table("episodes") as batch:
        batch.alter_column("season_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("episode_number", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("status", existing_type=sa.String(length=32), nullable=False, server_default="draft")
        batch.create_foreign_key("fk_episodes_season_id", "seasons", ["season_id"], ["id"], ondelete="CASCADE")
        batch.create_unique_constraint("uq_episode_number_per_season", ["season_id", "episode_number"])
        batch.create_index("ix_episodes_season_id", ["season_id"], unique=False)
        batch.create_index("ix_episodes_status", ["status"], unique=False)
        batch.create_index("ix_episodes_deleted_at", ["deleted_at"], unique=False)
        batch.drop_column("season")
        batch.drop_column("episode")
        batch.drop_column("duration")
        batch.drop_column("thumbnail")
        batch.drop_column("published")


def downgrade() -> None:
    # Non-destructive reverse is intentionally limited; prefer restore from backup.
    raise NotImplementedError("Downgrade of catalog administration migration is not supported")
