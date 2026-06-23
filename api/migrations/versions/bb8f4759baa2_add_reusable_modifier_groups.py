"""add reusable modifier groups

Revision ID: bb8f4759baa2
Revises: b1f2c3d4e5f6
Create Date: 2026-06-22 10:57:33.701171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bb8f4759baa2'
down_revision: Union[str, None] = 'b1f2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the reusable library alongside the old product-owned tables first.
    op.create_table('modifier_groups',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('select_type', sa.String(length=16), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("select_type in ('single','multi')", name=op.f('ck_modifier_groups_modifier_group_select_type')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_modifier_groups_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_modifier_groups'))
    )
    op.create_index(op.f('ix_modifier_groups_business_id'), 'modifier_groups', ['business_id'], unique=False)
    op.create_table('modifier_options',
    sa.Column('group_id', sa.UUID(), nullable=False),
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('price_delta', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_modifier_options_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['group_id'], ['modifier_groups.id'], name=op.f('fk_modifier_options_group_id_modifier_groups'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_modifier_options'))
    )
    op.create_index(op.f('ix_modifier_options_business_id'), 'modifier_options', ['business_id'], unique=False)
    op.create_index(op.f('ix_modifier_options_group_id'), 'modifier_options', ['group_id'], unique=False)
    op.create_table('product_modifier_groups',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('modifier_group_id', sa.UUID(), nullable=False),
    sa.Column('is_required', sa.Boolean(), nullable=False),
    sa.Column('min_select', sa.Integer(), nullable=False),
    sa.Column('max_select', sa.Integer(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('max_select is null or max_select >= 0', name=op.f('ck_product_modifier_groups_product_modifier_max_nonneg')),
    sa.CheckConstraint('min_select >= 0', name=op.f('ck_product_modifier_groups_product_modifier_min_nonneg')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_product_modifier_groups_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['modifier_group_id'], ['modifier_groups.id'], name=op.f('fk_product_modifier_groups_modifier_group_id_modifier_groups'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_modifier_groups_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_modifier_groups')),
    sa.UniqueConstraint('product_id', 'modifier_group_id', name='product_modifier_group_once')
    )
    op.create_index(op.f('ix_product_modifier_groups_business_id'), 'product_modifier_groups', ['business_id'], unique=False)
    op.create_index(op.f('ix_product_modifier_groups_modifier_group_id'), 'product_modifier_groups', ['modifier_group_id'], unique=False)
    op.create_index(op.f('ix_product_modifier_groups_product_id'), 'product_modifier_groups', ['product_id'], unique=False)
    # Preserve group and option IDs. Each legacy group was owned by exactly one
    # product, so its ID can also seed the first assignment ID safely.
    op.execute(
        """
        INSERT INTO modifier_groups
            (id, business_id, name, select_type, created_at, updated_at)
        SELECT id, business_id, name, select_type, now(), now()
        FROM product_option_groups
        """
    )
    op.execute(
        """
        INSERT INTO modifier_options
            (id, group_id, business_id, name, price_delta, is_default, sort_order)
        SELECT id, group_id, business_id, name, price_delta, is_default, sort_order
        FROM product_option_items
        """
    )
    op.execute(
        """
        INSERT INTO product_modifier_groups
            (id, business_id, product_id, modifier_group_id,
             is_required, min_select, max_select, sort_order)
        SELECT id, business_id, product_id, id,
               is_required, min_select, max_select, sort_order
        FROM product_option_groups
        """
    )

    op.drop_table('product_option_items')
    op.drop_table('product_option_groups')


def downgrade() -> None:
    # The old schema cannot represent sharing. Recreate one independent legacy
    # group per assignment; shared definitions are duplicated on downgrade.
    op.create_table('product_option_groups',
    sa.Column('business_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('product_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('select_type', sa.VARCHAR(length=16), autoincrement=False, nullable=False),
    sa.Column('is_required', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('min_select', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('max_select', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('sort_order', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.CheckConstraint("select_type::text = ANY (ARRAY['single'::character varying, 'multi'::character varying]::text[])", name=op.f('ck_product_option_groups_option_group_select_type')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_product_option_groups_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_option_groups_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_option_groups'))
    )
    op.create_index(op.f('ix_product_option_groups_product_id'), 'product_option_groups', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_option_groups_business_id'), 'product_option_groups', ['business_id'], unique=False)
    op.create_table('product_option_items',
    sa.Column('group_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('business_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('price_delta', sa.NUMERIC(precision=12, scale=2), autoincrement=False, nullable=False),
    sa.Column('is_default', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('sort_order', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_product_option_items_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['group_id'], ['product_option_groups.id'], name=op.f('fk_product_option_items_group_id_product_option_groups'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_option_items'))
    )
    op.create_index(op.f('ix_product_option_items_group_id'), 'product_option_items', ['group_id'], unique=False)
    op.create_index(op.f('ix_product_option_items_business_id'), 'product_option_items', ['business_id'], unique=False)

    op.execute(
        """
        INSERT INTO product_option_groups
            (id, business_id, product_id, name, select_type,
             is_required, min_select, max_select, sort_order)
        SELECT pmg.id, pmg.business_id, pmg.product_id, mg.name, mg.select_type,
               pmg.is_required, pmg.min_select, pmg.max_select, pmg.sort_order
        FROM product_modifier_groups pmg
        JOIN modifier_groups mg ON mg.id = pmg.modifier_group_id
        """
    )
    op.execute(
        """
        INSERT INTO product_option_items
            (id, group_id, business_id, name, price_delta, is_default, sort_order)
        SELECT gen_random_uuid(), pmg.id, mo.business_id, mo.name,
               mo.price_delta, mo.is_default, mo.sort_order
        FROM product_modifier_groups pmg
        JOIN modifier_options mo ON mo.group_id = pmg.modifier_group_id
        """
    )
    op.drop_index(op.f('ix_product_modifier_groups_product_id'), table_name='product_modifier_groups')
    op.drop_index(op.f('ix_product_modifier_groups_modifier_group_id'), table_name='product_modifier_groups')
    op.drop_index(op.f('ix_product_modifier_groups_business_id'), table_name='product_modifier_groups')
    op.drop_table('product_modifier_groups')
    op.drop_index(op.f('ix_modifier_options_group_id'), table_name='modifier_options')
    op.drop_index(op.f('ix_modifier_options_business_id'), table_name='modifier_options')
    op.drop_table('modifier_options')
    op.drop_index(op.f('ix_modifier_groups_business_id'), table_name='modifier_groups')
    op.drop_table('modifier_groups')
