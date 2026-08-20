"""media_packages origin sync state + origin_sync job support (hybrid CDN Phase 2).

Revision ID: 026_origin_package_sync_v1
Revises: 025_integration_configs_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "026_origin_package_sync_v1"
down_revision = "025_integration_configs_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_packages",
        sa.Column(
            "origin_sync_status",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "media_packages",
        sa.Column("origin_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media_packages",
        sa.Column("origin_sync_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "media_packages",
        sa.Column("origin_object_prefix", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "media_packages",
        sa.Column(
            "origin_sync_attempt",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "media_packages",
        sa.Column("origin_bytes_synced", sa.Integer(), nullable=True),
    )
    op.add_column(
        "media_packages",
        sa.Column("origin_object_count", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_media_packages_origin_sync_status",
        "media_packages",
        ["origin_sync_status"],
    )

    op.add_column(
        "media_processing_jobs",
        sa.Column("target_package_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_media_processing_jobs_target_package_id",
        "media_processing_jobs",
        ["target_package_id"],
    )
    # At most one active origin_sync job per package.
    op.create_index(
        "uq_media_processing_active_origin_sync",
        "media_processing_jobs",
        ["target_package_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'retry_wait') "
            "AND job_type = 'origin_sync' AND target_package_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status IN ('queued', 'running', 'retry_wait') "
            "AND job_type = 'origin_sync' AND target_package_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_media_processing_active_origin_sync", table_name="media_processing_jobs")
    op.drop_index("ix_media_processing_jobs_target_package_id", table_name="media_processing_jobs")
    op.drop_column("media_processing_jobs", "target_package_id")

    op.drop_index("ix_media_packages_origin_sync_status", table_name="media_packages")
    op.drop_column("media_packages", "origin_object_count")
    op.drop_column("media_packages", "origin_bytes_synced")
    op.drop_column("media_packages", "origin_sync_attempt")
    op.drop_column("media_packages", "origin_object_prefix")
    op.drop_column("media_packages", "origin_sync_error")
    op.drop_column("media_packages", "origin_synced_at")
    op.drop_column("media_packages", "origin_sync_status")
