"""External media source + nullable playback package + manual CMS credit fields.

Revision ID: 015_external_media_playability
Revises: 014_tmdb_demo_metadata

Option A (admin/demo external media):
- primary external source flag
- risk acknowledgement audit fields
- protection mode label (unprotected_direct)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "015_external_media_playability"
down_revision = "014_tmdb_demo_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("source_type", sa.String(length=32), server_default="uploaded", nullable=False),
    )
    op.add_column("media_assets", sa.Column("external_url", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("external_kind", sa.String(length=16), nullable=True))
    op.add_column(
        "media_assets", sa.Column("external_content_type", sa.String(length=128), nullable=True)
    )
    op.add_column("media_assets", sa.Column("external_content_length", sa.BigInteger(), nullable=True))
    op.add_column(
        "media_assets",
        sa.Column("external_accept_ranges", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "media_assets",
        sa.Column("external_validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media_assets",
        sa.Column("external_is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "media_assets",
        sa.Column(
            "external_protection_mode",
            sa.String(length=64),
            server_default="unprotected_direct",
            nullable=False,
        ),
    )
    op.add_column(
        "media_assets",
        sa.Column("external_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media_assets",
        sa.Column("external_acknowledged_by_admin_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_media_assets_source_type", "media_assets", ["source_type"])
    op.create_index("ix_media_assets_external_is_primary", "media_assets", ["external_is_primary"])

    # Promote newest validated external per movie/episode owner to primary.
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(movie_id, -1), COALESCE(episode_id, -1)
                   ORDER BY external_validated_at DESC NULLS LAST, updated_at DESC, id DESC
                 ) AS rn
          FROM media_assets
          WHERE source_type = 'external'
            AND external_url IS NOT NULL
            AND external_validated_at IS NOT NULL
            AND (movie_id IS NOT NULL OR episode_id IS NOT NULL)
        )
        UPDATE media_assets AS m
        SET external_is_primary = TRUE
        FROM ranked
        WHERE m.id = ranked.id AND ranked.rn = 1
        """
    )

    op.alter_column(
        "media_playback_sessions",
        "media_package_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )

    op.add_column("movies", sa.Column("producer", sa.String(length=512), server_default="", nullable=False))
    op.add_column("movies", sa.Column("writer", sa.String(length=512), server_default="", nullable=False))
    op.add_column("movies", sa.Column("studio", sa.String(length=512), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("movies", "studio")
    op.drop_column("movies", "writer")
    op.drop_column("movies", "producer")

    op.alter_column(
        "media_playback_sessions",
        "media_package_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )

    op.drop_index("ix_media_assets_external_is_primary", table_name="media_assets")
    op.drop_index("ix_media_assets_source_type", table_name="media_assets")
    op.drop_column("media_assets", "external_acknowledged_by_admin_id")
    op.drop_column("media_assets", "external_acknowledged_at")
    op.drop_column("media_assets", "external_protection_mode")
    op.drop_column("media_assets", "external_is_primary")
    op.drop_column("media_assets", "external_validated_at")
    op.drop_column("media_assets", "external_accept_ranges")
    op.drop_column("media_assets", "external_content_length")
    op.drop_column("media_assets", "external_content_type")
    op.drop_column("media_assets", "external_kind")
    op.drop_column("media_assets", "external_url")
    op.drop_column("media_assets", "source_type")
