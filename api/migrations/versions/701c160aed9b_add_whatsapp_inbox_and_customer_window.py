"""add whatsapp inbox and customer window

Revision ID: 701c160aed9b
Revises: e8a4d1c2b903
Create Date: 2026-06-24 23:44:04.271890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '701c160aed9b'
down_revision: Union[str, None] = 'e8a4d1c2b903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Spurious `server_default` drops that autogenerate proposed on pre-existing columns
    # (the models use Python-side defaults, not DB server defaults) were removed by hand —
    # this revision only adds the inbox table and the customer 24h-window column.
    op.create_table(
        'whatsapp_inbox',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=False),
        sa.Column('phone_number_id', sa.String(length=64), nullable=False),
        sa.Column('wa_phone', sa.String(length=32), nullable=False),
        sa.Column('thread_id', sa.String(length=128), nullable=False),
        sa.Column('msg_type', sa.String(length=32), nullable=False),
        sa.Column('reply_id', sa.String(length=256), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('confirmed', sa.Boolean(), nullable=False),
        sa.Column('profile_name', sa.String(length=255), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status in ('pending','processing','answered','done','failed','skipped')", name=op.f('ck_whatsapp_inbox_whatsapp_inbox_status')),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_whatsapp_inbox_business_id_businesses'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_inbox')),
        sa.UniqueConstraint('message_id', name=op.f('uq_whatsapp_inbox_message_id')),
    )
    op.create_index(op.f('ix_whatsapp_inbox_business_id'), 'whatsapp_inbox', ['business_id'], unique=False)
    op.create_index('ix_whatsapp_inbox_status', 'whatsapp_inbox', ['status'], unique=False)
    op.create_index('ix_whatsapp_inbox_thread_status', 'whatsapp_inbox', ['thread_id', 'status', 'created_at'], unique=False)
    op.add_column('customers', sa.Column('last_inbound_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'last_inbound_at')
    op.drop_index('ix_whatsapp_inbox_thread_status', table_name='whatsapp_inbox')
    op.drop_index('ix_whatsapp_inbox_status', table_name='whatsapp_inbox')
    op.drop_index(op.f('ix_whatsapp_inbox_business_id'), table_name='whatsapp_inbox')
    op.drop_table('whatsapp_inbox')
