"""orders: customer-facing short order_code

Adds ``orders.order_code`` — a short, unambiguous 6-char code (e.g. ``K7Q2X9``) shown to the
customer instead of the raw per-business ``order_no`` sequence (which both looks unprofessional
and leaks order volume). The code is derived deterministically from the existing atomic counter
(see ``app/core/order_code.py``), so it is unique per business by construction. Existing rows are
backfilled before the unique + NOT NULL constraints are applied.

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-06-27 10:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.order_code import business_salt, encode_order_code

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('order_code', sa.String(length=12), nullable=True))

    # Backfill existing orders from their (already-unique) order_no, per business.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, business_id, order_no FROM orders")).fetchall()
    for order_id, business_id, order_no in rows:
        code = encode_order_code(int(order_no), salt=business_salt(uuid.UUID(str(business_id))))
        bind.execute(
            sa.text("UPDATE orders SET order_code = :code WHERE id = :id"),
            {"code": code, "id": order_id},
        )

    op.create_unique_constraint('orders_business_code', 'orders', ['business_id', 'order_code'])
    op.alter_column('orders', 'order_code', nullable=False)


def downgrade() -> None:
    op.drop_constraint('orders_business_code', 'orders', type_='unique')
    op.drop_column('orders', 'order_code')
