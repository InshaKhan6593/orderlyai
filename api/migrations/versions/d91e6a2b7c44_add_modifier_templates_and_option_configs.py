"""add modifier templates and per-dish option configs

Revision ID: d91e6a2b7c44
Revises: c27b8f4e8a31
Create Date: 2026-06-22 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d91e6a2b7c44"
down_revision: Union[str, None] = "c27b8f4e8a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "modifier_groups",
        sa.Column("display_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "modifier_groups",
        sa.Column(
            "is_template",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.execute("UPDATE modifier_groups SET display_name = name")
    op.alter_column("modifier_groups", "display_name", nullable=False)

    op.add_column(
        "product_modifier_option_prices",
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.alter_column(
        "product_modifier_option_prices",
        "price_delta",
        existing_type=sa.Numeric(precision=12, scale=2),
        nullable=True,
    )
    op.execute(
        """
        UPDATE product_modifier_option_prices AS config
        SET is_default = option.is_default
        FROM modifier_options AS option
        WHERE option.id = config.modifier_option_id
        """
    )
    op.execute(
        """
        INSERT INTO product_modifier_option_prices
            (id, business_id, product_modifier_group_id, modifier_option_id,
             price_delta, is_default)
        SELECT gen_random_uuid(), assignment.business_id, assignment.id, option.id,
               NULL, option.is_default
        FROM product_modifier_groups AS assignment
        JOIN modifier_options AS option
          ON option.group_id = assignment.modifier_group_id
        LEFT JOIN product_modifier_option_prices AS config
          ON config.product_modifier_group_id = assignment.id
         AND config.modifier_option_id = option.id
        WHERE config.id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE product_modifier_option_prices AS config
        SET price_delta = option.price_delta
        FROM modifier_options AS option
        WHERE option.id = config.modifier_option_id
          AND config.price_delta IS NULL
        """
    )
    op.alter_column(
        "product_modifier_option_prices",
        "price_delta",
        existing_type=sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    op.drop_column("product_modifier_option_prices", "is_default")
    op.drop_column("modifier_groups", "is_template")
    op.drop_column("modifier_groups", "display_name")
