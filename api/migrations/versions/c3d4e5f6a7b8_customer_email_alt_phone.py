"""customer contact details: email + alternate_phone

Adds nullable ``customers.email`` and ``customers.alternate_phone`` so the WhatsApp ordering
agent can collect and reuse a customer's contact details across orders (name and
default_address already exist).

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('customers', sa.Column('alternate_phone', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'alternate_phone')
    op.drop_column('customers', 'email')
