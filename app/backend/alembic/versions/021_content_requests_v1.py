"""Content Requests V1: subscriber movie/series request queue.

Revision ID: 021_content_requests_v1
Revises: 020_content_translations_v1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_content_requests_v1"
down_revision = "020_content_translations_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("normalized_title", sa.String(length=255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.String(length=32), nullable=True),
        sa.Column("tmdb_url", sa.String(length=512), nullable=True),
        sa.Column("imdb_url", sa.String(length=512), nullable=True),
        sa.Column("preferred_language", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("public_response", sa.String(length=512), nullable=True),
        sa.Column("linked_movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "reviewed_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_type IN ('movie', 'series')",
            name="ck_content_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewing', 'approved', 'rejected', 'added', 'withdrawn')",
            name="ck_content_requests_status",
        ),
        sa.CheckConstraint(
            "(linked_movie_id IS NULL) OR (linked_series_id IS NULL)",
            name="ck_content_requests_one_link",
        ),
        sa.CheckConstraint(
            "(request_type != 'movie') OR (linked_series_id IS NULL)",
            name="ck_content_requests_movie_link",
        ),
        sa.CheckConstraint(
            "(request_type != 'series') OR (linked_movie_id IS NULL)",
            name="ck_content_requests_series_link",
        ),
    )
    op.create_index("ix_content_requests_subscriber_id", "content_requests", ["subscriber_id"])
    op.create_index("ix_content_requests_status", "content_requests", ["status"])
    op.create_index("ix_content_requests_request_type", "content_requests", ["request_type"])
    op.create_index("ix_content_requests_normalized_title", "content_requests", ["normalized_title"])
    op.create_index("ix_content_requests_tmdb_id", "content_requests", ["tmdb_id"])
    op.create_index("ix_content_requests_imdb_id", "content_requests", ["imdb_id"])
    op.create_index("ix_content_requests_created_at", "content_requests", ["created_at"])
    op.create_index(
        "ix_content_requests_subscriber_created",
        "content_requests",
        ["subscriber_id", "created_at"],
    )
    op.create_index(
        "ix_content_requests_demand",
        "content_requests",
        ["request_type", "normalized_title", "year"],
    )

    op.create_table(
        "content_request_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "content_request_id",
            sa.Integer(),
            sa.ForeignKey("content_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column(
            "actor_admin_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_subscriber_id",
            sa.Integer(),
            sa.ForeignKey("subscribers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_content_request_events_request_id",
        "content_request_events",
        ["content_request_id"],
    )
    op.create_index("ix_content_request_events_created_at", "content_request_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_content_request_events_created_at", table_name="content_request_events")
    op.drop_index("ix_content_request_events_request_id", table_name="content_request_events")
    op.drop_table("content_request_events")
    op.drop_index("ix_content_requests_demand", table_name="content_requests")
    op.drop_index("ix_content_requests_subscriber_created", table_name="content_requests")
    op.drop_index("ix_content_requests_created_at", table_name="content_requests")
    op.drop_index("ix_content_requests_imdb_id", table_name="content_requests")
    op.drop_index("ix_content_requests_tmdb_id", table_name="content_requests")
    op.drop_index("ix_content_requests_normalized_title", table_name="content_requests")
    op.drop_index("ix_content_requests_request_type", table_name="content_requests")
    op.drop_index("ix_content_requests_status", table_name="content_requests")
    op.drop_index("ix_content_requests_subscriber_id", table_name="content_requests")
    op.drop_table("content_requests")
