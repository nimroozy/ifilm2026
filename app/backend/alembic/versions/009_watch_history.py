"""watch history / progress

Revision ID: 009_watch_history
Revises: 008_publishing_workflow
Create Date: 2026-07-31

Replaces unused stub watch_history with normalized user_watch_progress.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_watch_history"
down_revision = "008_publishing_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_watch_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("playback_session_id", sa.String(length=36), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("position_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_watched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_watched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL AND episode_id IS NULL) OR (movie_id IS NULL AND episode_id IS NOT NULL)",
            name="ck_user_watch_progress_one_owner",
        ),
        sa.CheckConstraint("position_seconds >= 0", name="ck_user_watch_progress_position_nonneg"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_user_watch_progress_duration_pos"),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_user_watch_progress_percent_range",
        ),
        sa.UniqueConstraint("subscriber_id", "media_asset_id", name="uq_user_watch_progress_asset"),
    )
    op.create_index("ix_user_watch_progress_subscriber_id", "user_watch_progress", ["subscriber_id"])
    op.create_index("ix_user_watch_progress_media_asset_id", "user_watch_progress", ["media_asset_id"])
    op.create_index("ix_user_watch_progress_movie_id", "user_watch_progress", ["movie_id"])
    op.create_index("ix_user_watch_progress_episode_id", "user_watch_progress", ["episode_id"])
    op.create_index("ix_user_watch_progress_completed", "user_watch_progress", ["completed"])
    op.create_index("ix_user_watch_progress_last_watched_at", "user_watch_progress", ["last_watched_at"])
    op.create_index("ix_user_watch_progress_last_event_at", "user_watch_progress", ["last_event_at"])
    op.create_index(
        "ix_user_watch_progress_continue",
        "user_watch_progress",
        ["subscriber_id", "completed", "last_watched_at"],
    )
    op.create_index(
        "uq_user_watch_progress_movie",
        "user_watch_progress",
        ["subscriber_id", "movie_id"],
        unique=True,
        postgresql_where=sa.text("movie_id IS NOT NULL"),
        sqlite_where=sa.text("movie_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_watch_progress_episode",
        "user_watch_progress",
        ["subscriber_id", "episode_id"],
        unique=True,
        postgresql_where=sa.text("episode_id IS NOT NULL"),
        sqlite_where=sa.text("episode_id IS NOT NULL"),
    )

    # Stub table from 001 was never written by APIs; drop competing system.
    op.drop_table("watch_history")


def downgrade() -> None:
    op.create_table(
        "watch_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id"), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("poster", sa.String(length=1024), nullable=True),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index("uq_user_watch_progress_episode", table_name="user_watch_progress")
    op.drop_index("uq_user_watch_progress_movie", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_continue", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_last_event_at", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_last_watched_at", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_completed", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_episode_id", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_movie_id", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_media_asset_id", table_name="user_watch_progress")
    op.drop_index("ix_user_watch_progress_subscriber_id", table_name="user_watch_progress")
    op.drop_table("user_watch_progress")
