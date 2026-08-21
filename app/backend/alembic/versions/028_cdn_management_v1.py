"""Professional CDN management control plane.

Revision ID: 028_cdn_management_v1
Revises: 027_branch_cache_control_plane_v1
"""

import sqlalchemy as sa
from alembic import op

revision = "028_cdn_management_v1"
down_revision = "027_branch_cache_control_plane_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_cdn_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("host", sa.String(255), nullable=False, unique=True),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_username", sa.String(128), nullable=False),
        sa.Column("credential_type", sa.String(16), nullable=False, server_default="password"),
        sa.Column("credential_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("branch", sa.String(128), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("draining", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cache_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("cached_objects", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_titles", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_hits", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_misses", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bandwidth_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rtt_ms", sa.Integer(), nullable=True),
        sa.Column("software_version", sa.String(64), nullable=True),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("provision_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_managed_cdn_nodes_role", "managed_cdn_nodes", ["role"])
    op.create_table(
        "cdn_prefix_routes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cidr", sa.String(64), nullable=False, unique=True),
        sa.Column("prefix_length", sa.Integer(), nullable=False),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("managed_cdn_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_cdn_prefix_routes_prefix_length", "cdn_prefix_routes", ["prefix_length"])
    op.create_index("ix_cdn_prefix_routes_node_id", "cdn_prefix_routes", ["node_id"])
    op.create_table(
        "cdn_provision_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("managed_cdn_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("log_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "requested_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_cdn_provision_runs_node_id", "cdn_provision_runs", ["node_id"])


def downgrade() -> None:
    op.drop_table("cdn_provision_runs")
    op.drop_table("cdn_prefix_routes")
    op.drop_table("managed_cdn_nodes")
