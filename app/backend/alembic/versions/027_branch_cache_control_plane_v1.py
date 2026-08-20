"""Branch cache-node registry for hybrid CDN Phase 3 control plane.

Revision ID: 027_branch_cache_control_plane_v1
Revises: 026_origin_package_sync_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "027_branch_cache_control_plane_v1"
down_revision = "026_origin_package_sync_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branch_cache_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=64), nullable=False),
        sa.Column("branch_code", sa.String(length=64), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "draining",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "disabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("software_version", sa.String(length=64), nullable=True),
        sa.Column("protocol_version", sa.String(length=32), nullable=True),
        sa.Column("capacity_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "used_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "health_status",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("heartbeat_token_hash", sa.String(length=128), nullable=True),
        sa.Column("node_public_key_pem", sa.Text(), nullable=True),
        sa.Column("node_key_id", sa.String(length=64), nullable=True),
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
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["admin_users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("node_id", name="uq_branch_cache_nodes_node_id"),
    )
    op.create_index(
        "ix_branch_cache_nodes_site_id",
        "branch_cache_nodes",
        ["site_id"],
    )
    op.create_index(
        "ix_branch_cache_nodes_status",
        "branch_cache_nodes",
        ["status"],
    )
    op.create_index(
        "ix_branch_cache_nodes_health_status",
        "branch_cache_nodes",
        ["health_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_branch_cache_nodes_health_status", table_name="branch_cache_nodes")
    op.drop_index("ix_branch_cache_nodes_status", table_name="branch_cache_nodes")
    op.drop_index("ix_branch_cache_nodes_site_id", table_name="branch_cache_nodes")
    op.drop_table("branch_cache_nodes")
