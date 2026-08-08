"""Collections V1 tables.

Revision ID: 016_collections_v1
Revises: 015_external_media_playability
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "016_collections_v1"
down_revision = "015_external_media_playability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=280), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("short_description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("collection_type", sa.String(length=32), server_default="editorial", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("visibility", sa.String(length=32), server_default="public", nullable=False),
        sa.Column("poster_url", sa.String(length=1024), server_default="", nullable=False),
        sa.Column("backdrop_url", sa.String(length=1024), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("demo_owned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("demo_seed_version", sa.String(length=32), server_default="", nullable=False),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_collections_slug"),
    )
    op.create_index("ix_collections_title", "collections", ["title"])
    op.create_index("ix_collections_slug", "collections", ["slug"])
    op.create_index("ix_collections_collection_type", "collections", ["collection_type"])
    op.create_index("ix_collections_status", "collections", ["status"])
    op.create_index("ix_collections_visibility", "collections", ["visibility"])
    op.create_index("ix_collections_sort_order", "collections", ["sort_order"])
    op.create_index("ix_collections_is_featured", "collections", ["is_featured"])
    op.create_index("ix_collections_demo_owned", "collections", ["demo_owned"])
    op.create_index("ix_collections_published_at", "collections", ["published_at"])
    op.create_index("ix_collections_deleted_at", "collections", ["deleted_at"])

    op.create_table(
        "collection_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custom_title", sa.String(length=255), nullable=True),
        sa.Column("custom_description", sa.Text(), nullable=True),
        sa.Column("added_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL AND series_id IS NULL) OR (movie_id IS NULL AND series_id IS NOT NULL)",
            name="ck_collection_items_one_owner",
        ),
        sa.UniqueConstraint("collection_id", "position", name="uq_collection_items_position"),
    )
    op.create_index("ix_collection_items_collection_id", "collection_items", ["collection_id"])
    op.create_index("ix_collection_items_movie_id", "collection_items", ["movie_id"])
    op.create_index("ix_collection_items_series_id", "collection_items", ["series_id"])
    op.create_index(
        "uq_collection_items_movie",
        "collection_items",
        ["collection_id", "movie_id"],
        unique=True,
        postgresql_where=sa.text("movie_id IS NOT NULL"),
        sqlite_where=sa.text("movie_id IS NOT NULL"),
    )
    op.create_index(
        "uq_collection_items_series",
        "collection_items",
        ["collection_id", "series_id"],
        unique=True,
        postgresql_where=sa.text("series_id IS NOT NULL"),
        sqlite_where=sa.text("series_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_collection_items_series", table_name="collection_items")
    op.drop_index("uq_collection_items_movie", table_name="collection_items")
    op.drop_index("ix_collection_items_series_id", table_name="collection_items")
    op.drop_index("ix_collection_items_movie_id", table_name="collection_items")
    op.drop_index("ix_collection_items_collection_id", table_name="collection_items")
    op.drop_table("collection_items")

    op.drop_index("ix_collections_deleted_at", table_name="collections")
    op.drop_index("ix_collections_published_at", table_name="collections")
    op.drop_index("ix_collections_demo_owned", table_name="collections")
    op.drop_index("ix_collections_is_featured", table_name="collections")
    op.drop_index("ix_collections_sort_order", table_name="collections")
    op.drop_index("ix_collections_visibility", table_name="collections")
    op.drop_index("ix_collections_status", table_name="collections")
    op.drop_index("ix_collections_collection_type", table_name="collections")
    op.drop_index("ix_collections_slug", table_name="collections")
    op.drop_index("ix_collections_title", table_name="collections")
    op.drop_table("collections")
