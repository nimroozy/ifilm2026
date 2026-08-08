"""Catalog localized TMDB/manual metadata storage.

Revision ID: 020_content_translations_v1
Revises: 019_media_upload_reliability_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_content_translations_v1"
down_revision = "019_media_upload_reliability_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="tmdb"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "locale",
            "field_key",
            name="uq_content_translations_entity_locale_field",
        ),
    )
    op.create_index(
        "ix_content_translations_lookup",
        "content_translations",
        ["entity_type", "entity_id", "locale"],
    )
    op.create_index("ix_content_translations_source", "content_translations", ["source"])


def downgrade() -> None:
    op.drop_index("ix_content_translations_source", table_name="content_translations")
    op.drop_index("ix_content_translations_lookup", table_name="content_translations")
    op.drop_table("content_translations")
