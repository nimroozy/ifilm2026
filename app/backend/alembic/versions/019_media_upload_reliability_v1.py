"""Media upload reliability: admin audit events for delete/dedup.

Revision ID: 019_media_upload_reliability_v1
Revises: 018_movie_detail_experience_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "019_media_upload_reliability_v1"
down_revision = "018_movie_detail_experience_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    op.create_table(
        "media_admin_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("media_asset_id", sa.String(length=36), nullable=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("details", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_media_admin_events_event_type", "media_admin_events", ["event_type"])
    op.create_index("ix_media_admin_events_media_asset_id", "media_admin_events", ["media_asset_id"])
    op.create_index("ix_media_admin_events_admin_id", "media_admin_events", ["admin_id"])
    op.create_index("ix_media_admin_events_created_at", "media_admin_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_media_admin_events_created_at", table_name="media_admin_events")
    op.drop_index("ix_media_admin_events_admin_id", table_name="media_admin_events")
    op.drop_index("ix_media_admin_events_media_asset_id", table_name="media_admin_events")
    op.drop_index("ix_media_admin_events_event_type", table_name="media_admin_events")
    op.drop_table("media_admin_events")
