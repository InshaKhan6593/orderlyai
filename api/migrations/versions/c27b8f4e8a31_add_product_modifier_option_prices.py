"""add product modifier option prices

Revision ID: c27b8f4e8a31
Revises: bb8f4759baa2
Create Date: 2026-06-22 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c27b8f4e8a31"
down_revision: Union[str, None] = "bb8f4759baa2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_modifier_option_prices",
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("product_modifier_group_id", sa.UUID(), nullable=False),
        sa.Column("modifier_option_id", sa.UUID(), nullable=False),
        sa.Column("price_delta", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_product_modifier_option_prices_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["modifier_option_id"],
            ["modifier_options.id"],
            name=op.f(
                "fk_product_modifier_option_prices_modifier_option_id_modifier_options"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_modifier_group_id"],
            ["product_modifier_groups.id"],
            name=op.f(
                "fk_product_modifier_option_prices_product_modifier_group_id_product_modifier_groups"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_product_modifier_option_prices")
        ),
        sa.UniqueConstraint(
            "product_modifier_group_id",
            "modifier_option_id",
            name="product_modifier_option_price_once",
        ),
    )
    op.create_index(
        op.f("ix_product_modifier_option_prices_business_id"),
        "product_modifier_option_prices",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_modifier_option_prices_modifier_option_id"),
        "product_modifier_option_prices",
        ["modifier_option_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_modifier_option_prices_product_modifier_group_id"),
        "product_modifier_option_prices",
        ["product_modifier_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_product_modifier_option_prices_product_modifier_group_id"),
        table_name="product_modifier_option_prices",
    )
    op.drop_index(
        op.f("ix_product_modifier_option_prices_modifier_option_id"),
        table_name="product_modifier_option_prices",
    )
    op.drop_index(
        op.f("ix_product_modifier_option_prices_business_id"),
        table_name="product_modifier_option_prices",
    )
    op.drop_table("product_modifier_option_prices")
