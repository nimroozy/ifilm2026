"""TMDB-backed realistic demo metadata

Revision ID: 014_tmdb_demo_metadata
Revises: 013_app_settings
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014_tmdb_demo_metadata"
down_revision = "013_app_settings"
branch_labels = None
depends_on = None


def _json_list_default() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::json")
    return sa.text("'[]'")


def _add_catalog_columns(table: str) -> None:
    op.add_column(table, sa.Column("tmdb_id", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("metadata_source", sa.String(length=32), nullable=False, server_default=""))
    op.add_column(table, sa.Column("demo_owned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(table, sa.Column("demo_seed_version", sa.String(length=32), nullable=False, server_default=""))
    op.add_column(table, sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("metadata_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("logo_url", sa.String(length=1024), nullable=False, server_default=""))
    op.add_column(table, sa.Column("spoken_languages", sa.JSON(), nullable=False, server_default=_json_list_default()))
    op.add_column(table, sa.Column("trailer_provider", sa.String(length=32), nullable=False, server_default=""))
    op.add_column(table, sa.Column("trailer_key", sa.String(length=128), nullable=False, server_default=""))
    op.add_column(table, sa.Column("trailer_title", sa.String(length=255), nullable=False, server_default=""))
    op.add_column(table, sa.Column("trailer_official", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(table, sa.Column("trailer_language", sa.String(length=16), nullable=False, server_default=""))
    op.add_column(table, sa.Column("trailer_published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("has_demo_clip", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(f"ix_{table}_tmdb_id", table, ["tmdb_id"], unique=True)
    op.create_index(f"ix_{table}_demo_owned", table, ["demo_owned"], unique=False)


def _drop_catalog_columns(table: str) -> None:
    op.drop_index(f"ix_{table}_demo_owned", table_name=table)
    op.drop_index(f"ix_{table}_tmdb_id", table_name=table)
    for column in (
        "has_demo_clip",
        "trailer_published_at",
        "trailer_language",
        "trailer_official",
        "trailer_title",
        "trailer_key",
        "trailer_provider",
        "spoken_languages",
        "logo_url",
        "metadata_updated_at",
        "imported_at",
        "demo_seed_version",
        "demo_owned",
        "metadata_source",
        "tmdb_id",
    ):
        op.drop_column(table, column)


def upgrade() -> None:
    _add_catalog_columns("movies")
    _add_catalog_columns("series")

    op.add_column("episodes", sa.Column("tmdb_id", sa.Integer(), nullable=True))
    op.add_column("episodes", sa.Column("metadata_source", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("episodes", sa.Column("demo_owned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("episodes", sa.Column("demo_seed_version", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("episodes", sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("episodes", sa.Column("metadata_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("episodes", sa.Column("has_demo_clip", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_episodes_tmdb_id", "episodes", ["tmdb_id"], unique=False)
    op.create_index("ix_episodes_demo_owned", "episodes", ["demo_owned"], unique=False)
    op.create_unique_constraint("uq_episodes_series_tmdb_id", "episodes", ["series_id", "tmdb_id"])


def downgrade() -> None:
    op.drop_constraint("uq_episodes_series_tmdb_id", "episodes", type_="unique")
    op.drop_index("ix_episodes_demo_owned", table_name="episodes")
    op.drop_index("ix_episodes_tmdb_id", table_name="episodes")
    for column in (
        "has_demo_clip",
        "metadata_updated_at",
        "imported_at",
        "demo_seed_version",
        "demo_owned",
        "metadata_source",
        "tmdb_id",
    ):
        op.drop_column("episodes", column)

    _drop_catalog_columns("series")
    _drop_catalog_columns("movies")
