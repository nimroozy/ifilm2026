"""hls encoding pipeline

Revision ID: 006_hls_encoding
Revises: 005_media_processing
Create Date: 2026-07-31

Adds encoding profiles, media packages, media renditions, and a partial unique
index preventing duplicate active encode_hls jobs. Local filesystem only —
no CDN, R2, S3, playback, or DRM.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "006_hls_encoding"
down_revision = "005_media_processing"
branch_labels = None
depends_on = None

# Seed ladder: H.264 + AAC HLS VOD profiles (never upscale at encode time).
_PROFILE_SEED = [
    # name, label, height, video_bitrate, audio_bitrate, maxrate, bufsize, sort_order
    ("hls_240p", "240p", 240, 400_000, 64_000, 440_000, 800_000, 10),
    ("hls_360p", "360p", 360, 800_000, 96_000, 880_000, 1_600_000, 20),
    ("hls_480p", "480p", 480, 1_400_000, 128_000, 1_540_000, 2_800_000, 30),
    ("hls_720p", "720p", 720, 2_800_000, 128_000, 3_080_000, 5_600_000, 40),
    ("hls_1080p", "1080p", 1080, 5_000_000, 192_000, 5_500_000, 10_000_000, 50),
]


def upgrade() -> None:
    op.create_table(
        "media_encoding_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("video_bitrate", sa.Integer(), nullable=False),
        sa.Column("audio_bitrate", sa.Integer(), nullable=False),
        sa.Column("maxrate", sa.Integer(), nullable=False),
        sa.Column("bufsize", sa.Integer(), nullable=False),
        sa.Column("video_codec", sa.String(length=32), nullable=False, server_default="h264"),
        sa.Column("audio_codec", sa.String(length=32), nullable=False, server_default="aac"),
        sa.Column("video_profile", sa.String(length=32), nullable=False, server_default="main"),
        sa.Column("preset", sa.String(length=32), nullable=False, server_default="veryfast"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", name="uq_media_encoding_profiles_name"),
    )
    op.create_index(
        "ix_media_encoding_profiles_height", "media_encoding_profiles", ["height"]
    )
    op.create_index(
        "ix_media_encoding_profiles_enabled", "media_encoding_profiles", ["enabled"]
    )

    profiles = sa.table(
        "media_encoding_profiles",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("label", sa.String),
        sa.column("height", sa.Integer),
        sa.column("video_bitrate", sa.Integer),
        sa.column("audio_bitrate", sa.Integer),
        sa.column("maxrate", sa.Integer),
        sa.column("bufsize", sa.Integer),
        sa.column("video_codec", sa.String),
        sa.column("audio_codec", sa.String),
        sa.column("video_profile", sa.String),
        sa.column("preset", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        profiles,
        [
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "label": label,
                "height": height,
                "video_bitrate": vbr,
                "audio_bitrate": abr,
                "maxrate": maxrate,
                "bufsize": bufsize,
                "video_codec": "h264",
                "audio_codec": "aac",
                "video_profile": "main",
                "preset": "veryfast",
                "enabled": True,
                "sort_order": sort_order,
            }
            for name, label, height, vbr, abr, maxrate, bufsize, sort_order in _PROFILE_SEED
        ],
    )

    op.create_table(
        "media_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "processing_job_id",
            sa.String(length=36),
            sa.ForeignKey("media_processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("package_type", sa.String(length=32), nullable=False, server_default="hls_vod"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.String(length=1024), nullable=True),
        sa.Column("master_playlist_path", sa.String(length=1024), nullable=True),
        sa.Column("work_path", sa.String(length=1024), nullable=True),
        sa.Column("source_width", sa.Integer(), nullable=True),
        sa.Column("source_height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("segment_duration_seconds", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("rendition_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_packages_media_asset_id", "media_packages", ["media_asset_id"])
    op.create_index("ix_media_packages_status", "media_packages", ["status"])
    op.create_index("ix_media_packages_processing_job_id", "media_packages", ["processing_job_id"])

    op.create_table(
        "media_renditions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "package_id",
            sa.String(length=36),
            sa.ForeignKey("media_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.String(length=36),
            sa.ForeignKey("media_encoding_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("bandwidth", sa.Integer(), nullable=True),
        sa.Column("average_bandwidth", sa.Integer(), nullable=True),
        sa.Column("playlist_path", sa.String(length=1024), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("video_codec", sa.String(length=32), nullable=True),
        sa.Column("audio_codec", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_renditions_package_id", "media_renditions", ["package_id"])
    op.create_index("ix_media_renditions_label", "media_renditions", ["label"])

    # At most one active HLS encode job per asset.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_media_processing_active_encode_hls
        ON media_processing_jobs (media_asset_id, job_type)
        WHERE status IN ('queued', 'running', 'retry_wait') AND job_type = 'encode_hls'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_media_processing_active_encode_hls")
    op.drop_index("ix_media_renditions_label", table_name="media_renditions")
    op.drop_index("ix_media_renditions_package_id", table_name="media_renditions")
    op.drop_table("media_renditions")
    op.drop_index("ix_media_packages_processing_job_id", table_name="media_packages")
    op.drop_index("ix_media_packages_status", table_name="media_packages")
    op.drop_index("ix_media_packages_media_asset_id", table_name="media_packages")
    op.drop_table("media_packages")
    op.drop_index("ix_media_encoding_profiles_enabled", table_name="media_encoding_profiles")
    op.drop_index("ix_media_encoding_profiles_height", table_name="media_encoding_profiles")
    op.drop_table("media_encoding_profiles")
