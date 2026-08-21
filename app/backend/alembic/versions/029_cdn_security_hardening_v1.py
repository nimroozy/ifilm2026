"""CDN host-key pinning and authenticated heartbeats.

Revision ID: 029_cdn_security_hardening_v1
Revises: 028_cdn_management_v1
"""

import sqlalchemy as sa
from alembic import op

revision = "029_cdn_security_hardening_v1"
down_revision = "028_cdn_management_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("managed_cdn_nodes", sa.Column("ssh_host_key_fingerprint", sa.String(128)))
    op.add_column("managed_cdn_nodes", sa.Column("heartbeat_token_hash", sa.String(128)))


def downgrade() -> None:
    op.drop_column("managed_cdn_nodes", "heartbeat_token_hash")
    op.drop_column("managed_cdn_nodes", "ssh_host_key_fingerprint")
