"""Link media_tracks to source assets for production multi-track packaging.

Revision ID: 023_media_tracks_packaging_v1
Revises: 022_media_tracks_player_v1

Adds optional source_media_asset_id / source_stream_index so the HLS encoder can
consume admin-associated audio/subtitle sidecars (or embedded stream indexes).
UI labels remain frontend i18n — never store translated display strings here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023_media_tracks_packaging_v1"
down_revision = "022_media_tracks_player_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_tracks",
        sa.Column(
            "source_media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "media_tracks",
        sa.Column("source_stream_index", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_media_tracks_source_media_asset_id",
        "media_tracks",
        ["source_media_asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_tracks_source_media_asset_id", table_name="media_tracks")
    op.drop_column("media_tracks", "source_stream_index")
    op.drop_column("media_tracks", "source_media_asset_id")
