"""Alembic: remote media import companion table + active job uniqueness."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "030_remote_media_import_v1"
down_revision = "029_cdn_security_hardening_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remote_media_imports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "processing_job_id",
            sa.String(length=36),
            sa.ForeignKey("media_processing_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("destination", sa.String(length=32), nullable=False, server_default="local_origin"),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("source_url_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("source_url_display", sa.String(length=512), nullable=False),
        sa.Column("source_host", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("content_length", sa.BigInteger(), nullable=True),
        sa.Column("accept_ranges", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transfer_rate_bps", sa.BigInteger(), nullable=True),
        sa.Column("eta_seconds", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("transfer_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_remote_media_imports_job_id", "remote_media_imports", ["processing_job_id"], unique=True
    )
    op.create_index("ix_remote_media_imports_asset_id", "remote_media_imports", ["media_asset_id"])
    op.create_index(
        "ix_remote_media_imports_owner", "remote_media_imports", ["owner_type", "owner_id"]
    )
    op.create_index(
        "uq_remote_media_imports_active_owner",
        "remote_media_imports",
        ["owner_type", "owner_id"],
        unique=True,
        postgresql_where=sa.text("phase NOT IN ('completed', 'failed', 'cancelled')"),
        sqlite_where=sa.text("phase NOT IN ('completed', 'failed', 'cancelled')"),
    )
    op.create_index(
        "uq_media_processing_active_remote_import",
        "media_processing_jobs",
        ["media_asset_id", "job_type"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'retry_wait') AND job_type = 'remote_media_import'"
        ),
        sqlite_where=sa.text(
            "status IN ('queued', 'running', 'retry_wait') AND job_type = 'remote_media_import'"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_media_processing_active_remote_import", table_name="media_processing_jobs")
    op.drop_index("uq_remote_media_imports_active_owner", table_name="remote_media_imports")
    op.drop_index("ix_remote_media_imports_owner", table_name="remote_media_imports")
    op.drop_index("ix_remote_media_imports_asset_id", table_name="remote_media_imports")
    op.drop_index("ix_remote_media_imports_job_id", table_name="remote_media_imports")
    op.drop_table("remote_media_imports")
