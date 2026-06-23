"""add modifier option descriptions

Revision ID: f3b21c9d8a77
Revises: d91e6a2b7c44
Create Date: 2026-06-22 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b21c9d8a77"
down_revision: Union[str, None] = "d91e6a2b7c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "modifier_options",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("modifier_options", "description")
