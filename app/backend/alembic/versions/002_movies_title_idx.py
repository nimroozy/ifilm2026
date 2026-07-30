"""add movies title index

Revision ID: 002_movies_title_idx
Revises: 001_initial
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_movies_title_idx"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_movies_title", "movies", ["title"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_movies_title", table_name="movies")
