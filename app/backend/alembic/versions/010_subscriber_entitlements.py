"""subscriber auth entitlements

Revision ID: 010_subscriber_entitlements
Revises: 009_watch_history
Create Date: 2026-07-31

Local identity/entitlement/device/refresh tables for Phase 11.
Does not store Radius passwords. Radius remains the external identity source
when configured; local rows are snapshots for stable IDs and fail-closed cache.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010_subscriber_entitlements"
down_revision = "009_watch_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscribers",
        sa.Column("identity_provider", sa.String(length=32), nullable=False, server_default="local"),
    )
    op.add_column(
        "subscribers",
        sa.Column("external_subject", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "subscribers",
        sa.Column("service_status", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "subscribers",
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_subscribers_external_subject", "subscribers", ["external_subject"])
    op.create_index("ix_subscribers_identity_provider", "subscribers", ["identity_provider"])
    op.create_index("ix_subscribers_status", "subscribers", ["status"])
    op.create_index("ix_subscribers_service_status", "subscribers", ["service_status"])
    op.create_index("ix_subscribers_valid_until", "subscribers", ["valid_until"])
    op.create_index(
        "uq_subscribers_provider_subject",
        "subscribers",
        ["identity_provider", "external_subject"],
        unique=True,
        postgresql_where=sa.text("external_subject IS NOT NULL"),
        sqlite_where=sa.text("external_subject IS NOT NULL"),
    )

    op.create_table(
        "subscriber_entitlement_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "subscriber_id",
            sa.Integer(),
            sa.ForeignKey("subscribers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("account_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("service_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("package_name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("branch_code", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denial_code", sa.String(length=64), nullable=True),
        sa.Column("safe_reason", sa.String(length=255), nullable=True),
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_subscriber_entitlement_snapshots_subscriber_id",
        "subscriber_entitlement_snapshots",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_subscriber_entitlement_snapshots_checked_at",
        "subscriber_entitlement_snapshots",
        ["checked_at"],
    )
    op.create_index(
        "ix_subscriber_entitlement_snapshots_expires_at",
        "subscriber_entitlement_snapshots",
        ["expires_at"],
    )
    op.create_index(
        "ix_subscriber_entitlement_snapshots_allowed",
        "subscriber_entitlement_snapshots",
        ["allowed"],
    )

    op.create_table(
        "subscriber_device_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "subscriber_id",
            sa.Integer(),
            sa.ForeignKey("subscribers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_device_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("device_type", sa.String(length=32), nullable=False, server_default="desktop"),
        sa.Column("browser", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=255), nullable=True),
        sa.UniqueConstraint(
            "subscriber_id",
            "client_device_id",
            name="uq_subscriber_device_client_id",
        ),
    )
    op.create_index(
        "ix_subscriber_device_sessions_subscriber_id",
        "subscriber_device_sessions",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_subscriber_device_sessions_client_device_id",
        "subscriber_device_sessions",
        ["client_device_id"],
    )
    op.create_index(
        "ix_subscriber_device_sessions_revoked_at",
        "subscriber_device_sessions",
        ["revoked_at"],
    )
    op.create_index(
        "ix_subscriber_device_sessions_active",
        "subscriber_device_sessions",
        ["subscriber_id", "revoked_at"],
    )

    op.create_table(
        "subscriber_refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "subscriber_id",
            sa.Integer(),
            sa.ForeignKey("subscribers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_session_id",
            sa.Integer(),
            sa.ForeignKey("subscriber_device_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Integer(), nullable=True),
        sa.Column("reuse_detected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_subscriber_refresh_tokens_token_hash",
        "subscriber_refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_subscriber_refresh_tokens_subscriber_id",
        "subscriber_refresh_tokens",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_subscriber_refresh_tokens_family_id",
        "subscriber_refresh_tokens",
        ["family_id"],
    )
    op.create_index(
        "ix_subscriber_refresh_tokens_device_session_id",
        "subscriber_refresh_tokens",
        ["device_session_id"],
    )
    op.create_index(
        "ix_subscriber_refresh_tokens_expires_at",
        "subscriber_refresh_tokens",
        ["expires_at"],
    )

    op.add_column(
        "media_playback_sessions",
        sa.Column(
            "device_session_id",
            sa.Integer(),
            sa.ForeignKey("subscriber_device_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_media_playback_sessions_device_session_id",
        "media_playback_sessions",
        ["device_session_id"],
    )

    # Clear locally stored Radius/fixture passwords — provider-backed accounts must not keep them.
    op.execute(
        sa.text(
            "UPDATE subscribers SET hashed_password = NULL "
            "WHERE radius_synced = true OR identity_provider IN ('fixture', 'radius')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_media_playback_sessions_device_session_id", table_name="media_playback_sessions")
    op.drop_column("media_playback_sessions", "device_session_id")

    op.drop_index("ix_subscriber_refresh_tokens_expires_at", table_name="subscriber_refresh_tokens")
    op.drop_index(
        "ix_subscriber_refresh_tokens_device_session_id", table_name="subscriber_refresh_tokens"
    )
    op.drop_index("ix_subscriber_refresh_tokens_family_id", table_name="subscriber_refresh_tokens")
    op.drop_index(
        "ix_subscriber_refresh_tokens_subscriber_id", table_name="subscriber_refresh_tokens"
    )
    op.drop_index("ix_subscriber_refresh_tokens_token_hash", table_name="subscriber_refresh_tokens")
    op.drop_table("subscriber_refresh_tokens")

    op.drop_index("ix_subscriber_device_sessions_active", table_name="subscriber_device_sessions")
    op.drop_index("ix_subscriber_device_sessions_revoked_at", table_name="subscriber_device_sessions")
    op.drop_index(
        "ix_subscriber_device_sessions_client_device_id", table_name="subscriber_device_sessions"
    )
    op.drop_index(
        "ix_subscriber_device_sessions_subscriber_id", table_name="subscriber_device_sessions"
    )
    op.drop_table("subscriber_device_sessions")

    op.drop_index(
        "ix_subscriber_entitlement_snapshots_allowed",
        table_name="subscriber_entitlement_snapshots",
    )
    op.drop_index(
        "ix_subscriber_entitlement_snapshots_expires_at",
        table_name="subscriber_entitlement_snapshots",
    )
    op.drop_index(
        "ix_subscriber_entitlement_snapshots_checked_at",
        table_name="subscriber_entitlement_snapshots",
    )
    op.drop_index(
        "ix_subscriber_entitlement_snapshots_subscriber_id",
        table_name="subscriber_entitlement_snapshots",
    )
    op.drop_table("subscriber_entitlement_snapshots")

    op.drop_index("uq_subscribers_provider_subject", table_name="subscribers")
    op.drop_index("ix_subscribers_valid_until", table_name="subscribers")
    op.drop_index("ix_subscribers_service_status", table_name="subscribers")
    op.drop_index("ix_subscribers_status", table_name="subscribers")
    op.drop_index("ix_subscribers_identity_provider", table_name="subscribers")
    op.drop_index("ix_subscribers_external_subject", table_name="subscribers")
    op.drop_column("subscribers", "valid_until")
    op.drop_column("subscribers", "valid_from")
    op.drop_column("subscribers", "service_status")
    op.drop_column("subscribers", "max_devices")
    op.drop_column("subscribers", "external_subject")
    op.drop_column("subscribers", "identity_provider")
