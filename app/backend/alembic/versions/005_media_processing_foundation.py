"""media processing foundation

Revision ID: 005_media_processing
Revises: 004_media_upload
Create Date: 2026-07-31

Adds media_processing_jobs, media_processing_job_events, and probe metadata
columns on media_assets. Does not implement HLS, CDN, or playback.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_media_processing"
down_revision = "004_media_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("container_format", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("overall_bitrate", sa.BigInteger(), nullable=True))
    op.add_column("media_assets", sa.Column("video_codec", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("video_profile", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("display_aspect_ratio", sa.String(length=32), nullable=True))
    op.add_column("media_assets", sa.Column("video_frame_rate", sa.Float(), nullable=True))
    op.add_column("media_assets", sa.Column("video_bitrate", sa.BigInteger(), nullable=True))
    op.add_column("media_assets", sa.Column("pixel_format", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("audio_codec", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("audio_channels", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("audio_channel_layout", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("audio_sample_rate", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("audio_bitrate", sa.BigInteger(), nullable=True))
    op.add_column("media_assets", sa.Column("audio_stream_count", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("subtitle_stream_count", sa.Integer(), nullable=True))
    op.add_column("media_assets", sa.Column("probe_json", sa.JSON(), nullable=True))
    op.add_column("media_assets", sa.Column("probe_version", sa.String(length=64), nullable=True))
    op.add_column("media_assets", sa.Column("probed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_media_assets_processing_status", "media_assets", ["processing_status"])

    op.create_table(
        "media_processing_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=32), nullable=False, server_default="probe"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_processing_jobs_status", "media_processing_jobs", ["status"])
    op.create_index(
        "ix_media_processing_jobs_media_asset_id", "media_processing_jobs", ["media_asset_id"]
    )
    op.create_index(
        "ix_media_processing_jobs_next_retry_at", "media_processing_jobs", ["next_retry_at"]
    )
    op.create_index("ix_media_processing_jobs_priority", "media_processing_jobs", ["priority"])
    op.create_index(
        "ix_media_processing_jobs_heartbeat_at", "media_processing_jobs", ["heartbeat_at"]
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_media_processing_active_probe
        ON media_processing_jobs (media_asset_id, job_type)
        WHERE status IN ('queued', 'running', 'retry_wait') AND job_type = 'probe'
        """
    )

    op.create_table(
        "media_processing_job_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("media_processing_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_media_processing_job_events_job_id", "media_processing_job_events", ["job_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_media_processing_job_events_job_id", table_name="media_processing_job_events")
    op.drop_table("media_processing_job_events")
    op.execute("DROP INDEX IF EXISTS uq_media_processing_active_probe")
    op.drop_index("ix_media_processing_jobs_heartbeat_at", table_name="media_processing_jobs")
    op.drop_index("ix_media_processing_jobs_priority", table_name="media_processing_jobs")
    op.drop_index("ix_media_processing_jobs_next_retry_at", table_name="media_processing_jobs")
    op.drop_index("ix_media_processing_jobs_media_asset_id", table_name="media_processing_jobs")
    op.drop_index("ix_media_processing_jobs_status", table_name="media_processing_jobs")
    op.drop_table("media_processing_jobs")

    op.drop_index("ix_media_assets_processing_status", table_name="media_assets")
    for col in (
        "probed_at",
        "probe_version",
        "probe_json",
        "subtitle_stream_count",
        "audio_stream_count",
        "audio_bitrate",
        "audio_sample_rate",
        "audio_channel_layout",
        "audio_channels",
        "audio_codec",
        "pixel_format",
        "video_bitrate",
        "video_frame_rate",
        "display_aspect_ratio",
        "video_profile",
        "video_codec",
        "overall_bitrate",
        "container_format",
    ):
        op.drop_column("media_assets", col)
