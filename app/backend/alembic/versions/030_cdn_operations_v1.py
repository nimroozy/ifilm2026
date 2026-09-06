"""CDN operations: node priority/serving URL/usage/managed keys, route notes, resumable runs.

Revision ID: 030_cdn_operations_v1
Revises: 029_cdn_security_hardening_v1
"""

import sqlalchemy as sa
from alembic import op

revision = "030_cdn_operations_v1"
down_revision = "029_cdn_security_hardening_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "managed_cdn_nodes",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column("managed_cdn_nodes", sa.Column("serve_base_url", sa.String(512)))
    op.add_column("managed_cdn_nodes", sa.Column("disk_used_bytes", sa.BigInteger()))
    op.add_column("managed_cdn_nodes", sa.Column("cache_used_bytes", sa.BigInteger()))
    op.add_column("managed_cdn_nodes", sa.Column("last_error", sa.Text()))
    op.add_column("managed_cdn_nodes", sa.Column("last_error_at", sa.DateTime(timezone=True)))
    op.add_column("managed_cdn_nodes", sa.Column("managed_key_ciphertext", sa.LargeBinary()))
    op.add_column("managed_cdn_nodes", sa.Column("managed_key_public", sa.Text()))
    op.add_column("managed_cdn_nodes", sa.Column("managed_key_fingerprint", sa.String(128)))
    op.add_column(
        "managed_cdn_nodes",
        sa.Column("high_watermark_pct", sa.Integer(), nullable=False, server_default="90"),
    )
    op.add_column(
        "managed_cdn_nodes",
        sa.Column("low_watermark_pct", sa.Integer(), nullable=False, server_default="80"),
    )
    op.add_column("managed_cdn_nodes", sa.Column("provisioned_at", sa.DateTime(timezone=True)))
    op.add_column("managed_cdn_nodes", sa.Column("os_release", sa.String(64)))
    op.add_column("managed_cdn_nodes", sa.Column("last_ssh_test_at", sa.DateTime(timezone=True)))
    op.add_column("managed_cdn_nodes", sa.Column("last_ssh_test_ok", sa.Boolean()))
    op.add_column("managed_cdn_nodes", sa.Column("observed_host_key_fingerprint", sa.String(128)))

    op.add_column("cdn_prefix_routes", sa.Column("notes", sa.Text()))

    op.add_column("cdn_provision_runs", sa.Column("step", sa.String(64)))
    op.add_column(
        "cdn_provision_runs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("cdn_provision_runs", sa.Column("error_code", sa.String(64)))
    op.add_column("cdn_provision_runs", sa.Column("resume_from_step", sa.String(64)))
    op.add_column("cdn_provision_runs", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("cdn_provision_runs", sa.Column("claimed_by", sa.String(128)))
    op.create_index("ix_cdn_provision_runs_status", "cdn_provision_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cdn_provision_runs_status", table_name="cdn_provision_runs")
    for column in (
        "claimed_by",
        "claimed_at",
        "resume_from_step",
        "error_code",
        "attempt",
        "step",
    ):
        op.drop_column("cdn_provision_runs", column)
    op.drop_column("cdn_prefix_routes", "notes")
    for column in (
        "observed_host_key_fingerprint",
        "last_ssh_test_ok",
        "last_ssh_test_at",
        "os_release",
        "provisioned_at",
        "low_watermark_pct",
        "high_watermark_pct",
        "managed_key_fingerprint",
        "managed_key_public",
        "managed_key_ciphertext",
        "last_error_at",
        "last_error",
        "cache_used_bytes",
        "disk_used_bytes",
        "serve_base_url",
        "priority",
    ):
        op.drop_column("managed_cdn_nodes", column)
