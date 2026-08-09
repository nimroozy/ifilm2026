"""Media tracks for multi-audio / subtitle player metadata.

Revision ID: 022_media_tracks_player_v1
Revises: 021_content_requests_v1

Stores language-coded track rows (audio/subtitle). UI labels are derived in the
frontend via i18n — never store translated display strings here.

Watch progress continues to use existing user_watch_progress (009).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "022_media_tracks_player_v1"
down_revision = "021_content_requests_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("track_type", sa.String(length=16), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=False),
        sa.Column("label_key", sa.String(length=64), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_dubbed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hls_group_id", sa.String(length=64), nullable=True),
        sa.Column("hls_name", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "track_type IN ('audio', 'subtitle')",
            name="ck_media_tracks_type",
        ),
    )
    op.create_index("ix_media_tracks_media_asset_id", "media_tracks", ["media_asset_id"])
    op.create_index(
        "ix_media_tracks_asset_type_lang",
        "media_tracks",
        ["media_asset_id", "track_type", "language_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_media_tracks_asset_type_lang", table_name="media_tracks")
    op.drop_index("ix_media_tracks_media_asset_id", table_name="media_tracks")
    op.drop_table("media_tracks")
