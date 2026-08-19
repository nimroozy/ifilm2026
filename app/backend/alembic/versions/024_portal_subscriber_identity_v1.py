"""portal branch-scoped subscriber identity — drop global username uniqueness.

Revision ID: 024_portal_subscriber_identity_v1
Revises: 023_media_tracks_packaging_v1

Same Internet username may exist in multiple SAS branches. Portal A1 keys
local subscribers by (identity_provider, external_subject) e.g. NMZ:1210000.
The global UNIQUE on subscribers.username must be removed so those rows can
coexist. Index on username is retained for lookup performance.

Portal identity uniqueness is enforced by the partial unique index
``uq_subscribers_provider_subject`` (created in 010; ensured here).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "024_portal_subscriber_identity_v1"
down_revision = "023_media_tracks_packaging_v1"
branch_labels = None
depends_on = None

_PROVIDER_SUBJECT_INDEX = "uq_subscribers_provider_subject"
_USERNAME_INDEX = "ix_subscribers_username"


def _username_unique_constraint_names(inspector) -> set[str]:
    names: set[str] = set()
    for uq in inspector.get_unique_constraints("subscribers"):
        cols = list(uq.get("column_names") or [])
        if cols == ["username"] and uq.get("name"):
            names.add(uq["name"])
    return names


def _username_unique_index_names(inspector) -> set[str]:
    names: set[str] = set()
    for idx in inspector.get_indexes("subscribers"):
        cols = list(idx.get("column_names") or [])
        if idx.get("unique") and cols == ["username"] and idx.get("name"):
            names.add(idx["name"])
    return names


def _ensure_provider_subject_unique(inspector) -> None:
    """Ensure partial UNIQUE (identity_provider, external_subject) WHERE subject NOT NULL."""
    indexes = {i["name"]: i for i in inspector.get_indexes("subscribers")}
    if _PROVIDER_SUBJECT_INDEX in indexes:
        return
    op.create_index(
        _PROVIDER_SUBJECT_INDEX,
        "subscribers",
        ["identity_provider", "external_subject"],
        unique=True,
        postgresql_where=sa.text("external_subject IS NOT NULL"),
        sqlite_where=sa.text("external_subject IS NOT NULL"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    # Revision id is 33 chars; stock alembic_version.version_num is VARCHAR(32).
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE VARCHAR(64)"
            )
        )
    elif bind.dialect.name == "sqlite":
        # SQLite ignores length; no-op for type width.
        pass

    inspector = sa.inspect(bind)

    # Postgres UNIQUE column constraints appear in both unique_constraints and
    # indexes. Drop via constraint first, then re-inspect before any DROP INDEX.
    for name in sorted(_username_unique_constraint_names(inspector)):
        op.drop_constraint(name, "subscribers", type_="unique")

    inspector = sa.inspect(bind)
    for name in sorted(_username_unique_index_names(inspector)):
        op.drop_index(name, table_name="subscribers")

    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("subscribers")}
    if _USERNAME_INDEX not in indexes:
        op.create_index(_USERNAME_INDEX, "subscribers", ["username"], unique=False)

    inspector = sa.inspect(bind)
    _ensure_provider_subject_unique(inspector)


def downgrade() -> None:
    """Restore global username uniqueness only when safe.

    After portal mode allows the same Internet username in different branches,
    recreating a global UNIQUE on username would fail or force data mutation.
    Never delete/merge subscriber rows here — fail with a clear error instead.
    """
    bind = op.get_bind()
    dupes = bind.execute(
        sa.text(
            """
            SELECT username, COUNT(*) AS cnt
            FROM subscribers
            GROUP BY username
            HAVING COUNT(*) > 1
            ORDER BY username
            """
        )
    ).fetchall()
    if dupes:
        sample = ", ".join(f"{row[0]}×{row[1]}" for row in dupes[:8])
        more = "" if len(dupes) <= 8 else f" (+{len(dupes) - 8} more)"
        raise RuntimeError(
            "Cannot restore global UNIQUE on subscribers.username: duplicate "
            f"usernames exist ({sample}{more}). Portal branch-scoped identities "
            "must be resolved manually before downgrading "
            "024_portal_subscriber_identity_v1; subscriber rows were not modified."
        )

    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("subscribers")}
    if _USERNAME_INDEX in indexes:
        op.drop_index(_USERNAME_INDEX, table_name="subscribers")
    op.create_index(_USERNAME_INDEX, "subscribers", ["username"], unique=True)
