"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("permissions", sa.JSON(), nullable=True),
    )
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("admin_roles.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_title", sa.String(length=255), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("age_rating", sa.String(length=32), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("director", sa.String(length=255), nullable=True),
        sa.Column("cast", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("poster", sa.String(length=1024), nullable=True),
        sa.Column("backdrop", sa.String(length=1024), nullable=True),
        sa.Column("audio", sa.JSON(), nullable=True),
        sa.Column("subtitles", sa.JSON(), nullable=True),
        sa.Column("qualities", sa.JSON(), nullable=True),
        sa.Column("dubbed", sa.JSON(), nullable=True),
        sa.Column("featured", sa.Boolean(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("hls_path", sa.String(length=1024), nullable=True),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_title", sa.String(length=255), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("age_rating", sa.String(length=32), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("seasons", sa.Integer(), nullable=True),
        sa.Column("episode_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("poster", sa.String(length=1024), nullable=True),
        sa.Column("backdrop", sa.String(length=1024), nullable=True),
        sa.Column("audio", sa.JSON(), nullable=True),
        sa.Column("subtitles", sa.JSON(), nullable=True),
        sa.Column("dubbed", sa.JSON(), nullable=True),
        sa.Column("new_episode", sa.Boolean(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail", sa.String(length=1024), nullable=True),
        sa.Column("hls_path", sa.String(length=1024), nullable=True),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("branch", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("package", sa.String(length=100), nullable=True),
        sa.Column("expiration", sa.String(length=32), nullable=True),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewing_time", sa.Integer(), nullable=True),
        sa.Column("radius_synced", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("browser", sa.String(length=100), nullable=True),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("current", sa.Boolean(), nullable=True),
    )
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE")),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("subscriber_id", "content_type", "content_id", name="uq_watchlist"),
    )
    op.create_table(
        "watch_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE")),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("poster", sa.String(length=1024), nullable=True),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("stored_path", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "encoding_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_file", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("upload_job_id", sa.Integer(), sa.ForeignKey("upload_jobs.id"), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("worker", sa.String(length=100), nullable=True),
        sa.Column("qualities", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("output_hls_path", sa.String(length=1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("eta_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("cdn", sa.String(length=255), nullable=True),
        sa.Column("ip_ranges", sa.String(length=512), nullable=True),
        sa.Column("active_users", sa.Integer(), nullable=True),
        sa.Column("concurrent_viewers", sa.Integer(), nullable=True),
        sa.Column("streaming_traffic", sa.String(length=64), nullable=True),
        sa.Column("cdn_status", sa.String(length=32), nullable=True),
    )
    op.create_table(
        "cdn_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("base_url", sa.String(length=1024), nullable=True),
        sa.Column("storage_capacity", sa.Integer(), nullable=True),
        sa.Column("storage_used", sa.Integer(), nullable=True),
        sa.Column("network_usage", sa.Integer(), nullable=True),
        sa.Column("current_viewers", sa.Integer(), nullable=True),
        sa.Column("cached_titles", sa.Integer(), nullable=True),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("cache_hit_rate", sa.Float(), nullable=True),
        sa.Column("branch", sa.String(length=100), nullable=True),
    )
    op.create_table(
        "cdn_sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("cdn_nodes.id"), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("hls_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for table in [
        "cdn_sync_jobs",
        "cdn_nodes",
        "branches",
        "encoding_jobs",
        "upload_jobs",
        "watch_history",
        "watchlist_items",
        "devices",
        "subscribers",
        "episodes",
        "series",
        "movies",
        "admin_users",
        "admin_roles",
    ]:
        op.drop_table(table)
