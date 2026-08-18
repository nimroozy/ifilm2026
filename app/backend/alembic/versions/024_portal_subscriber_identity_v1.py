"""portal branch-scoped subscriber identity — drop global username uniqueness.

Revision ID: 024_portal_subscriber_identity_v1
Revises: 023_media_tracks_packaging_v1

Same Internet username may exist in multiple SAS branches. Portal A1 keys
local subscribers by (identity_provider, external_subject) e.g. NMZ:1210000.
The global UNIQUE on subscribers.username must be removed so those rows can
coexist. Index on username is retained for lookup performance.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "024_portal_subscriber_identity_v1"
down_revision = "023_media_tracks_packaging_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uniques = {u["name"] for u in inspector.get_unique_constraints("subscribers")}
    indexes = {i["name"]: i for i in inspector.get_indexes("subscribers")}

    # SQLAlchemy unique=True → typically subscribers_username_key (Postgres)
    # or a unique index named similarly on SQLite.
    if "subscribers_username_key" in uniques:
        op.drop_constraint("subscribers_username_key", "subscribers", type_="unique")
    elif "uq_subscribers_username" in uniques:
        op.drop_constraint("uq_subscribers_username", "subscribers", type_="unique")

    for name, idx in list(indexes.items()):
        cols = list(idx.get("column_names") or [])
        if idx.get("unique") and cols == ["username"]:
            op.drop_index(name, table_name="subscribers")
            op.create_index("ix_subscribers_username", "subscribers", ["username"], unique=False)
            break
    else:
        # Ensure a non-unique username index exists.
        if "ix_subscribers_username" not in indexes:
            op.create_index("ix_subscribers_username", "subscribers", ["username"], unique=False)


def downgrade() -> None:
    # Downgrade may fail if duplicate usernames already exist — expected.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("subscribers")}
    if "ix_subscribers_username" in indexes:
        op.drop_index("ix_subscribers_username", table_name="subscribers")
    op.create_index("ix_subscribers_username", "subscribers", ["username"], unique=True)
