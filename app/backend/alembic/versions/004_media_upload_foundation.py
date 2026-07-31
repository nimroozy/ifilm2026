"""media upload foundation

Revision ID: 004_media_upload
Revises: 003_catalog_admin
Create Date: 2026-07-31

Adds media_assets and upload_sessions for local streaming uploads.
Does not implement encoding, HLS, CDN, or playback.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_media_upload"
down_revision = "003_catalog_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="SET NULL"), nullable=True),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="originals"),
        sa.Column("upload_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(CASE WHEN movie_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN series_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN season_id IS NOT NULL THEN 1 ELSE 0 END)"
            " + (CASE WHEN episode_id IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="ck_media_assets_single_owner",
        ),
    )
    op.create_index("ix_media_assets_checksum_sha256", "media_assets", ["checksum_sha256"])
    op.create_index("ix_media_assets_upload_status", "media_assets", ["upload_status"])
    op.create_index("ix_media_assets_movie_id", "media_assets", ["movie_id"])
    op.create_index("ix_media_assets_series_id", "media_assets", ["series_id"])
    op.create_index("ix_media_assets_season_id", "media_assets", ["season_id"])
    op.create_index("ix_media_assets_episode_id", "media_assets", ["episode_id"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("temp_path", sa.String(length=1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upload_sessions_media_asset_id", "upload_sessions", ["media_asset_id"])
    op.create_index("ix_upload_sessions_status", "upload_sessions", ["status"])


def downgrade() -> None:
    op.drop_table("upload_sessions")
    op.drop_table("media_assets")
