"""review hardening: unique business hours per day + order list indexes

Revision ID: b1f2c3d4e5f6
Revises: 305384d945d4
Create Date: 2026-06-20 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b1f2c3d4e5f6"
down_revision: Union[str, None] = "305384d945d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pre-flight: rows that violate the new constraint were allowed before, so
    # collapse any existing duplicates (keep the lowest id per business+weekday)
    # before adding it — otherwise create_unique_constraint fails on live data.
    op.execute(
        """
        DELETE FROM business_hours a
        USING business_hours b
        WHERE a.business_id = b.business_id
          AND a.day_of_week = b.day_of_week
          AND a.id > b.id
        """
    )
    # One row per weekday per business.
    op.create_unique_constraint(
        "uq_business_hours_business_dow",
        "business_hours",
        ["business_id", "day_of_week"],
    )
    # Dashboard order lists: newest-first per business, optionally by status.
    op.create_index(
        "ix_orders_business_created",
        "orders",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_business_status_created",
        "orders",
        ["business_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_business_status_created", table_name="orders")
    op.drop_index("ix_orders_business_created", table_name="orders")
    op.drop_constraint(
        "uq_business_hours_business_dow", "business_hours", type_="unique"
    )
