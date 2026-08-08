"""Movie detail experience: stored TMDB cast credits.

Revision ID: 018_movie_detail_experience_v1
Revises: 017_watchlist_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "018_movie_detail_experience_v1"
down_revision = "017_watchlist_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "movie_cast_credits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tmdb_person_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("character_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("profile_path", sa.String(length=512), server_default="", nullable=False),
        sa.Column("profile_url", sa.String(length=1024), server_default="", nullable=False),
        sa.Column("credit_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("movie_id", "tmdb_person_id", name="uq_movie_cast_credits_person"),
    )
    op.create_index("ix_movie_cast_credits_movie_id", "movie_cast_credits", ["movie_id"])
    op.create_index("ix_movie_cast_credits_order", "movie_cast_credits", ["movie_id", "credit_order"])

    op.create_table(
        "series_cast_credits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tmdb_person_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("character_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("profile_path", sa.String(length=512), server_default="", nullable=False),
        sa.Column("profile_url", sa.String(length=1024), server_default="", nullable=False),
        sa.Column("credit_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("series_id", "tmdb_person_id", name="uq_series_cast_credits_person"),
    )
    op.create_index("ix_series_cast_credits_series_id", "series_cast_credits", ["series_id"])
    op.create_index("ix_series_cast_credits_order", "series_cast_credits", ["series_id", "credit_order"])

    op.add_column(
        "movies",
        sa.Column("credits_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "series",
        sa.Column("credits_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("series", "credits_synced_at")
    op.drop_column("movies", "credits_synced_at")
    op.drop_index("ix_series_cast_credits_order", table_name="series_cast_credits")
    op.drop_index("ix_series_cast_credits_series_id", table_name="series_cast_credits")
    op.drop_table("series_cast_credits")
    op.drop_index("ix_movie_cast_credits_order", table_name="movie_cast_credits")
    op.drop_index("ix_movie_cast_credits_movie_id", table_name="movie_cast_credits")
    op.drop_table("movie_cast_credits")
