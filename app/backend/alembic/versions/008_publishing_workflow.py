"""publishing workflow

Revision ID: 008_publishing_workflow
Revises: 007_streaming_service
Create Date: 2026-07-31

Adds publication lifecycle columns on movies/series/seasons/episodes and
media_publication_events history table. Status remains VARCHAR(32); new
lifecycle values are application-validated (no PostgreSQL enum alteration).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_publishing_workflow"
down_revision = "007_streaming_service"
branch_labels = None
depends_on = None

_ENTITY_TABLES = ("movies", "series", "seasons", "episodes")

_SHARED_COLUMNS: list[tuple[str, sa.Column]] = [
    ("published_by", sa.Column("published_by", sa.Integer(), nullable=True)),
    ("submitted_for_review_at", sa.Column("submitted_for_review_at", sa.DateTime(timezone=True), nullable=True)),
    ("submitted_for_review_by", sa.Column("submitted_for_review_by", sa.Integer(), nullable=True)),
    ("approved_at", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
    ("approved_by", sa.Column("approved_by", sa.Integer(), nullable=True)),
    ("scheduled_publish_at", sa.Column("scheduled_publish_at", sa.DateTime(timezone=True), nullable=True)),
    ("unpublished_at", sa.Column("unpublished_at", sa.DateTime(timezone=True), nullable=True)),
    ("unpublished_by", sa.Column("unpublished_by", sa.Integer(), nullable=True)),
    ("archived_at", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)),
    ("archived_by", sa.Column("archived_by", sa.Integer(), nullable=True)),
    ("publication_version", sa.Column("publication_version", sa.Integer(), nullable=False, server_default="0")),
    ("publication_reason", sa.Column("publication_reason", sa.Text(), nullable=True)),
]


def upgrade() -> None:
    # Seasons previously lacked published_at.
    op.add_column("seasons", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_seasons_published_at", "seasons", ["published_at"])

    for table in _ENTITY_TABLES:
        for _name, column in _SHARED_COLUMNS:
            op.add_column(table, column)
        op.create_index(f"ix_{table}_scheduled_publish_at", table, ["scheduled_publish_at"])

    # Backfill archived_at from soft-deleted rows.
    for table in _ENTITY_TABLES:
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET archived_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
                    status = CASE
                        WHEN status = 'archived' THEN status
                        WHEN deleted_at IS NOT NULL THEN 'archived'
                        ELSE status
                    END
                WHERE deleted_at IS NOT NULL AND archived_at IS NULL
                """
            )
        )

    op.create_table(
        "media_publication_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="transition"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_media_publication_events_entity",
        "media_publication_events",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index("ix_media_publication_events_to_status", "media_publication_events", ["to_status"])
    op.create_index("ix_media_publication_events_event_type", "media_publication_events", ["event_type"])
    op.create_index("ix_media_publication_events_created_at", "media_publication_events", ["created_at"])
    op.create_index("ix_media_publication_events_actor_user_id", "media_publication_events", ["actor_user_id"])


def downgrade() -> None:
    op.drop_table("media_publication_events")

    for table in _ENTITY_TABLES:
        op.drop_index(f"ix_{table}_scheduled_publish_at", table_name=table)
        for name, _column in reversed(_SHARED_COLUMNS):
            op.drop_column(table, name)

    op.drop_index("ix_seasons_published_at", table_name="seasons")
    op.drop_column("seasons", "published_at")
