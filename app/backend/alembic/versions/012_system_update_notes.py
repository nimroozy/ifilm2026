"""optional notes column for system update jobs (backward-compatible)

Revision ID: 012_system_update_notes
Revises: 011_system_updates
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012_system_update_notes"
down_revision = "011_system_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_update_jobs",
        sa.Column("operator_notes", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_update_jobs", "operator_notes")
