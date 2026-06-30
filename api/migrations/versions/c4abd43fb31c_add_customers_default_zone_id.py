"""add customers.default_zone_id

Adds ``customers.default_zone_id`` — the customer's usual delivery AREA (a delivery_zones FK),
saved on delivery orders so a returning customer's area + street address prefill at checkout
instead of being re-asked. ``ON DELETE SET NULL`` so deleting a zone just clears the preference
(and the agent re-validates the saved zone is still active before reusing it).

Hand-trimmed from autogenerate: the unrelated server-default diffs and the LangGraph ``checkpoint*``
tables (created/owned by the checkpointer's ``setup()``, NOT Alembic) were removed.

Revision ID: c4abd43fb31c
Revises: e5f6a7b8c9d0
Create Date: 2026-06-29 15:39:55.944636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4abd43fb31c'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('default_zone_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_customers_default_zone_id_delivery_zones'),
        'customers', 'delivery_zones',
        ['default_zone_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_customers_default_zone_id_delivery_zones'), 'customers', type_='foreignkey'
    )
    op.drop_column('customers', 'default_zone_id')
