"""system updates jobs and history

Revision ID: 011_system_updates
Revises: 010_subscriber_entitlements
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_system_updates"
down_revision = "010_subscriber_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_update_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("state", sa.String(length=64), nullable=False, index=True),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="stable"),
        sa.Column("current_version", sa.String(length=64), nullable=True),
        sa.Column("target_version", sa.String(length=64), nullable=True),
        sa.Column("actor_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("backup_id", sa.String(length=128), nullable=True),
        sa.Column("previous_migration_head", sa.String(length=128), nullable=True),
        sa.Column("resulting_migration_head", sa.String(length=128), nullable=True),
        sa.Column("release_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("preflight_ok", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("rollback_result", sa.String(length=64), nullable=True),
        sa.Column("agent_job_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "system_update_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("system_update_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("system_update_events")
    op.drop_table("system_update_jobs")
