"""Watchlist V1: movie/series XOR membership + continue-watching dismiss.

Revision ID: 017_watchlist_v1
Revises: 016_collections_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "017_watchlist_v1"
down_revision = "016_collections_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("movie_id", sa.Integer(), nullable=True))
    op.add_column("watchlist_items", sa.Column("series_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_watchlist_items_movie_id_movies",
        "watchlist_items",
        "movies",
        ["movie_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_watchlist_items_series_id_series",
        "watchlist_items",
        "series",
        ["series_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Backfill from legacy polymorphic columns (table was never exposed via API).
    op.execute(
        sa.text(
            """
            UPDATE watchlist_items
            SET movie_id = content_id
            WHERE lower(content_type) = 'movie' AND content_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE watchlist_items
            SET series_id = content_id
            WHERE lower(content_type) IN ('series', 'show', 'tv') AND content_id IS NOT NULL
            """
        )
    )
    # Drop rows that could not be mapped to a valid XOR owner.
    op.execute(
        sa.text(
            """
            DELETE FROM watchlist_items
            WHERE (movie_id IS NULL AND series_id IS NULL)
               OR (movie_id IS NOT NULL AND series_id IS NOT NULL)
            """
        )
    )
    # Drop rows pointing at missing catalog entities.
    op.execute(
        sa.text(
            """
            DELETE FROM watchlist_items w
            WHERE w.movie_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM movies m WHERE m.id = w.movie_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM watchlist_items w
            WHERE w.series_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM series s WHERE s.id = w.series_id)
            """
        )
    )

    op.drop_constraint("uq_watchlist", "watchlist_items", type_="unique")
    op.drop_column("watchlist_items", "content_type")
    op.drop_column("watchlist_items", "content_id")

    op.create_check_constraint(
        "ck_watchlist_items_one_owner",
        "watchlist_items",
        "(movie_id IS NOT NULL AND series_id IS NULL) OR (movie_id IS NULL AND series_id IS NOT NULL)",
    )
    op.create_index("ix_watchlist_items_movie_id", "watchlist_items", ["movie_id"])
    op.create_index("ix_watchlist_items_series_id", "watchlist_items", ["series_id"])
    op.create_index(
        "uq_watchlist_items_movie",
        "watchlist_items",
        ["subscriber_id", "movie_id"],
        unique=True,
        postgresql_where=sa.text("movie_id IS NOT NULL"),
    )
    op.create_index(
        "uq_watchlist_items_series",
        "watchlist_items",
        ["subscriber_id", "series_id"],
        unique=True,
        postgresql_where=sa.text("series_id IS NOT NULL"),
    )
    op.create_index(
        "ix_watchlist_items_subscriber_created",
        "watchlist_items",
        ["subscriber_id", "created_at"],
    )

    op.add_column(
        "user_watch_progress",
        sa.Column(
            "hidden_from_continue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_user_watch_progress_hidden_from_continue",
        "user_watch_progress",
        ["hidden_from_continue"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_watch_progress_hidden_from_continue", table_name="user_watch_progress")
    op.drop_column("user_watch_progress", "hidden_from_continue")

    op.drop_index("ix_watchlist_items_subscriber_created", table_name="watchlist_items")
    op.drop_index("uq_watchlist_items_series", table_name="watchlist_items")
    op.drop_index("uq_watchlist_items_movie", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_series_id", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_movie_id", table_name="watchlist_items")
    op.drop_constraint("ck_watchlist_items_one_owner", "watchlist_items", type_="check")

    op.add_column("watchlist_items", sa.Column("content_type", sa.String(length=32), nullable=True))
    op.add_column("watchlist_items", sa.Column("content_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE watchlist_items
            SET content_type = 'movie', content_id = movie_id
            WHERE movie_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE watchlist_items
            SET content_type = 'series', content_id = series_id
            WHERE series_id IS NOT NULL
            """
        )
    )
    op.execute(sa.text("DELETE FROM watchlist_items WHERE content_type IS NULL OR content_id IS NULL"))
    op.alter_column("watchlist_items", "content_type", nullable=False)
    op.alter_column("watchlist_items", "content_id", nullable=False)

    op.drop_constraint("fk_watchlist_items_series_id_series", "watchlist_items", type_="foreignkey")
    op.drop_constraint("fk_watchlist_items_movie_id_movies", "watchlist_items", type_="foreignkey")
    op.drop_column("watchlist_items", "series_id")
    op.drop_column("watchlist_items", "movie_id")
    op.create_unique_constraint(
        "uq_watchlist",
        "watchlist_items",
        ["subscriber_id", "content_type", "content_id"],
    )
