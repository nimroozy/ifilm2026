"""hls streaming service

Revision ID: 007_streaming_service
Revises: 006_hls_encoding
Create Date: 2026-07-31

Adds:
- media_playback_sessions
- explicit active-package columns on media_packages
- partial unique index: at most one active HLS package per asset

Backfill rule (deterministic):
For each media_asset_id, among packages where status='completed' and
package_type='hls_vod', activate the single newest row ordered by
completed_at DESC NULLS LAST, created_at DESC, id DESC.
All other packages remain inactive. Failed/cancelled/in-progress packages
are never activated.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_streaming_service"
down_revision = "006_hls_encoding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_packages",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "media_packages",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media_packages",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_media_packages_active_requires_completed",
        "media_packages",
        "is_active = false OR status = 'completed'",
    )
    op.create_index(
        "uq_media_packages_one_active_hls",
        "media_packages",
        ["media_asset_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND package_type = 'hls_vod'"),
        sqlite_where=sa.text("is_active = 1 AND package_type = 'hls_vod'"),
    )
    op.create_index("ix_media_packages_is_active", "media_packages", ["is_active"])

    # Deterministic backfill of newest completed package per asset.
    # PostgreSQL UPDATE ... FROM. For SQLite alembic tests this revision is
    # exercised against PostgreSQL in CI; unit tests use metadata.create_all.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE media_packages AS p
                SET is_active = true,
                    activated_at = COALESCE(p.completed_at, p.created_at)
                FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY media_asset_id
                               ORDER BY completed_at DESC NULLS LAST,
                                        created_at DESC,
                                        id DESC
                           ) AS rn
                    FROM media_packages
                    WHERE status = 'completed'
                      AND package_type = 'hls_vod'
                ) AS ranked
                WHERE p.id = ranked.id
                  AND ranked.rn = 1
                """
            )
        )
    else:
        # SQLite-compatible deterministic backfill.
        op.execute(
            sa.text(
                """
                UPDATE media_packages
                SET is_active = 1,
                    activated_at = COALESCE(completed_at, created_at)
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY media_asset_id
                                   ORDER BY completed_at DESC,
                                            created_at DESC,
                                            id DESC
                               ) AS rn
                        FROM media_packages
                        WHERE status = 'completed'
                          AND package_type = 'hls_vod'
                    ) AS ranked
                    WHERE rn = 1
                )
                """
            )
        )

    op.create_table(
        "media_playback_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.String(length=36),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_package_id",
            sa.String(length=36),
            sa.ForeignKey("media_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_media_playback_sessions_token_hash",
        "media_playback_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_media_playback_sessions_media_asset_id",
        "media_playback_sessions",
        ["media_asset_id"],
    )
    op.create_index(
        "ix_media_playback_sessions_media_package_id",
        "media_playback_sessions",
        ["media_package_id"],
    )
    op.create_index(
        "ix_media_playback_sessions_principal",
        "media_playback_sessions",
        ["principal_type", "principal_id"],
    )
    op.create_index(
        "ix_media_playback_sessions_status", "media_playback_sessions", ["status"]
    )
    op.create_index(
        "ix_media_playback_sessions_expires_at",
        "media_playback_sessions",
        ["expires_at"],
    )
    op.create_index(
        "ix_media_playback_sessions_created_at",
        "media_playback_sessions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("media_playback_sessions")
    op.drop_index("ix_media_packages_is_active", table_name="media_packages")
    op.drop_index("uq_media_packages_one_active_hls", table_name="media_packages")
    op.drop_constraint(
        "ck_media_packages_active_requires_completed",
        "media_packages",
        type_="check",
    )
    op.drop_column("media_packages", "superseded_at")
    op.drop_column("media_packages", "activated_at")
    op.drop_column("media_packages", "is_active")
